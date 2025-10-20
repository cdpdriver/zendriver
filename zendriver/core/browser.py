from __future__ import annotations

import asyncio
import copy
import http
import http.cookiejar
import json
import logging
import pathlib
import pickle
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import warnings
from collections import defaultdict
from typing import List, Tuple, Union, Any

import asyncio_atexit

from .. import cdp
from . import tab, util
from ._contradict import ContraDict
from .config import BrowserType, Config, PathLike, is_posix
from .connection import Connection

logger = logging.getLogger(__name__)


class Browser:
    """
    The Browser object is the "root" of the hierarchy and contains a reference
    to the browser parent process.
    there should usually be only 1 instance of this.

    All opened tabs, extra browser screens and resources will not cause a new Browser process,
    but rather create additional :class:`zendriver.Tab` objects.

    So, besides starting your instance and first/additional tabs, you don't actively use it a lot under normal conditions.

    Tab objects will represent and control
     - tabs (as you know them)
     - browser windows (new window)
     - iframe
     - background processes

    note:
    the Browser object is not instantiated by __init__ but using the asynchronous :meth:`zendriver.Browser.create` method.

    note:
    in Chromium based browsers, there is a parent process which keeps running all the time, even if
    there are no visible browser windows. sometimes it's stubborn to close it, so make sure after using
    this library, the browser is correctly and fully closed/exited/killed.

    """

    _process: subprocess.Popen[bytes] | None
    _process_pid: int | None
    _http: HTTPApi | None = None
    _cookies: CookieJar | None = None
    _update_target_info_mutex: asyncio.Lock = asyncio.Lock()

    config: Config
    connection: Connection | None

    @classmethod
    async def create(
        cls,
        config: Config | None = None,
        *,
        user_data_dir: PathLike | None = None,
        headless: bool = False,
        user_agent: str | None = None,
        browser_executable_path: PathLike | None = None,
        browser: BrowserType = "auto",
        browser_args: List[str] | None = None,
        sandbox: bool = True,
        lang: str | None = None,
        host: str | None = None,
        port: int | None = None,
        **kwargs: Any,
    ) -> Browser:
        """
        entry point for creating an instance
        """
        if not config:
            config = Config(
                user_data_dir=user_data_dir,
                headless=headless,
                user_agent=user_agent,
                browser_executable_path=browser_executable_path,
                browser=browser,
                browser_args=browser_args or [],
                sandbox=sandbox,
                lang=lang,
                host=host,
                port=port,
                **kwargs,
            )
        instance = cls(config)
        await instance.start()

        async def browser_atexit() -> None:
            if not instance.stopped:
                await instance.stop()
            await instance._cleanup_temporary_profile()

        asyncio_atexit.register(browser_atexit)

        return instance

    def __init__(self, config: Config):
        """
        constructor. to create a instance, use :py:meth:`Browser.create(...)`

        :param config:
        """

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "{0} objects of this class are created using await {0}.create()".format(
                    self.__class__.__name__
                )
            )
        # weakref.finalize(self, self._quit, self)

        # each instance gets it's own copy so this class gets a copy that it can
        # use to help manage the browser instance data (needed for multiple browsers)
        self.config = copy.deepcopy(config)

        self.targets: List[Connection] = []
        """current targets (all types)"""
        self.info: ContraDict | None = None
        self._target = None
        self._process = None
        self._process_pid = None
        self._is_updating = asyncio.Event()
        self.connection = None
        logger.debug("Session object initialized: %s" % vars(self))

    @property
    def websocket_url(self) -> str:
        if not self.info:
            raise RuntimeError("Browser not yet started. use await browser.start()")

        return self.info.webSocketDebuggerUrl  # type: ignore

    @property
    def main_tab(self) -> tab.Tab | None:
        """returns the target which was launched with the browser"""
        results = sorted(self.targets, key=lambda x: x.type_ == "page", reverse=True)
        if len(results) > 0:
            result = results[0]
            if isinstance(result, tab.Tab):
                return result
        return None

    @property
    def tabs(self) -> List[tab.Tab]:
        """returns the current targets which are of type "page"
        :return:
        """
        tabs = filter(lambda item: item.type_ == "page", self.targets)
        return list(tabs)  # type: ignore

    @property
    def cookies(self) -> CookieJar:
        if not self._cookies:
            self._cookies = CookieJar(self)
        return self._cookies

    @property
    def stopped(self) -> bool:
        if self._process and self._process.returncode is None:
            return False
        return True
        # return (self._process and self._process.returncode) or False

    async def wait(self, time: Union[float, int] = 1) -> Browser:
        """wait for <time> seconds. important to use, especially in between page navigation

        :param time:
        :return:
        """
        return await asyncio.sleep(time, result=self)

    sleep = wait
    """alias for wait"""

    async def _handle_target_update(
        self,
        event: Union[
            cdp.target.TargetInfoChanged,
            cdp.target.TargetDestroyed,
            cdp.target.TargetCreated,
            cdp.target.TargetCrashed,
        ],
    ) -> None:
        """this is an internal handler which updates the targets when chrome emits the corresponding event"""

        async with self._update_target_info_mutex:
            if isinstance(event, cdp.target.TargetInfoChanged):
                target_info = event.target_info

                current_tab = next(
                    filter(
                        lambda item: item.target_id == target_info.target_id,
                        self.targets,
                    )
                )
                current_target = current_tab.target

                if logger.getEffectiveLevel() <= 10:
                    changes = util.compare_target_info(current_target, target_info)
                    changes_string = ""
                    for change in changes:
                        key, old, new = change
                        changes_string += f"\n{key}: {old} => {new}\n"
                    logger.debug(
                        "target #%d has changed: %s"
                        % (self.targets.index(current_tab), changes_string)
                    )

                current_tab.target = target_info

            elif isinstance(event, cdp.target.TargetCreated):
                target_info = event.target_info
                from .tab import Tab

                new_target = Tab(
                    (
                        f"ws://{self.config.host}:{self.config.port}"
                        f"/devtools/{target_info.type_ or 'page'}"  # all types are 'page' internally in chrome apparently
                        f"/{target_info.target_id}"
                    ),
                    target=target_info,
                    browser=self,
                )

                self.targets.append(new_target)

                logger.debug("target #%d created => %s", len(self.targets), new_target)

            elif isinstance(event, cdp.target.TargetDestroyed):
                current_tab = next(
                    filter(lambda item: item.target_id == event.target_id, self.targets)
                )
                logger.debug(
                    "target removed. id # %d => %s"
                    % (self.targets.index(current_tab), current_tab)
                )
                self.targets.remove(current_tab)

    async def get(
        self, url: str = "about:blank", new_tab: bool = False, new_window: bool = False
    ) -> tab.Tab:
        """top level get. utilizes the first tab to retrieve given url.

        convenience function known from selenium.
        this function handles waits/sleeps and detects when DOM events fired, so it's the safest
        way of navigating.

        :param url: the url to navigate to
        :param new_tab: open new tab
        :param new_window:  open new window
        :return: Page
        :raises: asyncio.TimeoutError
        """
        if not self.connection:
            raise RuntimeError("Browser not yet started. use await browser.start()")

        future = asyncio.get_running_loop().create_future()
        event_type = cdp.target.TargetInfoChanged

        async def get_handler(event: cdp.target.TargetInfoChanged) -> None:
            if future.done():
                return

            # ignore TargetInfoChanged event from browser startup
            if event.target_info.url != "about:blank" or (
                url == "about:blank" and event.target_info.url == "about:blank"
            ):
                future.set_result(event)

        self.connection.add_handler(event_type, get_handler)

        if new_tab or new_window:
            # create new target using the browser session
            target_id = await self.connection.send(
                cdp.target.create_target(
                    url, new_window=new_window, enable_begin_frame_control=True
                )
            )
            # get the connection matching the new target_id from our inventory
            connection: tab.Tab = next(
                filter(
                    lambda item: item.type_ == "page" and item.target_id == target_id,
                    self.targets,
                )
            )  # type: ignore
            connection.browser = self
        else:
            # first tab from browser.tabs
            connection = next(filter(lambda item: item.type_ == "page", self.targets))  # type: ignore
            # use the tab to navigate to new url
            await connection.send(cdp.page.navigate(url))
            connection.browser = self

        await asyncio.wait_for(future, 10)
        self.connection.remove_handlers(event_type, get_handler)

        return connection

    async def start(self) -> Browser:
        """launches the actual browser"""
        if not self:
            raise ValueError(
                "Cannot be called as a class method. Use `await Browser.create()` to create a new instance"
            )

        if self._process or self._process_pid:
            if self._process and self._process.returncode is not None:
                return await self.create(config=self.config)
            warnings.warn("ignored! this call has no effect when already running.")
            return self

        connect_existing = False
        if self.config.host is not None and self.config.port is not None:
            connect_existing = True
        else:
            self.config.host = "127.0.0.1"
            self.config.port = util.free_port()

        if not connect_existing:
            logger.debug(
                "BROWSER EXECUTABLE PATH: %s", self.config.browser_executable_path
            )
            if not pathlib.Path(self.config.browser_executable_path).exists():
                raise FileNotFoundError(
                    (
                        """
                    ---------------------
                    Could not determine browser executable.
                    ---------------------
                    Make sure your browser is installed in the default location (path).
                    If you are sure about the browser executable, you can specify it using
                    the `browser_executable_path='{}` parameter."""
                    ).format(
                        "/path/to/browser/executable"
                        if is_posix
                        else "c:/path/to/your/browser.exe"
                    )
                )

        if getattr(self.config, "_extensions", None):  # noqa
            self.config.add_argument(
                "--load-extension=%s"
                % ",".join(str(_) for _ in self.config._extensions)
            )  # noqa

        if self.config.lang is not None:
            self.config.add_argument(f"--lang={self.config.lang}")

        exe = self.config.browser_executable_path
        params = self.config()
        params.append("about:blank")

        logger.info(
            "starting\n\texecutable :%s\n\narguments:\n%s", exe, "\n\t".join(params)
        )
        if not connect_existing:
            self._process = util._start_process(exe, params, is_posix)
            self._process_pid = self._process.pid

        self._http = HTTPApi((self.config.host, self.config.port))
        util.get_registered_instances().add(self)
        await asyncio.sleep(self.config.browser_connection_timeout)
        for _ in range(self.config.browser_connection_max_tries):
            if await self.test_connection():
                break

            await asyncio.sleep(self.config.browser_connection_timeout)

        if not self.info:
            if self._process is not None:
                stderr = await util._read_process_stderr(self._process)
                logger.info(
                    "Browser stderr: %s", stderr if stderr else "No output from browser"
                )

            await self.stop()
            raise Exception(
                (
                    """
                ---------------------
                Failed to connect to browser
                ---------------------
                One of the causes could be when you are running as root.
                In that case you need to pass no_sandbox=True
                """
                )
            )

        self.connection = Connection(self.info.webSocketDebuggerUrl, _owner=self)

        if self.config.autodiscover_targets:
            logger.info("enabling autodiscover targets")

            # self.connection.add_handler(
            #     cdp.target.TargetInfoChanged, self._handle_target_update
            # )
            # self.connection.add_handler(
            #     cdp.target.TargetCreated, self._handle_target_update
            # )
            # self.connection.add_handler(
            #     cdp.target.TargetDestroyed, self._handle_target_update
            # )
            # self.connection.add_handler(
            #     cdp.target.TargetCreated, self._handle_target_update
            # )
            #
            self.connection.handlers[cdp.target.TargetInfoChanged] = [
                self._handle_target_update
            ]
            self.connection.handlers[cdp.target.TargetCreated] = [
                self._handle_target_update
            ]
            self.connection.handlers[cdp.target.TargetDestroyed] = [
                self._handle_target_update
            ]
            self.connection.handlers[cdp.target.TargetCrashed] = [
                self._handle_target_update
            ]
            await self.connection.send(cdp.target.set_discover_targets(discover=True))
        await self.update_targets()
        return self

    async def test_connection(self) -> bool:
        if not self._http:
            raise ValueError("HTTPApi not yet initialized")

        try:
            self.info = ContraDict(await self._http.get("version"), silent=True)
            return True
        except Exception:
            logger.debug("Could not start", exc_info=True)
            return False

    async def grant_all_permissions(self) -> None:
        """
        grant permissions for:
            accessibilityEvents
            audioCapture
            backgroundSync
            backgroundFetch
            clipboardReadWrite
            clipboardSanitizedWrite
            displayCapture
            durableStorage
            geolocation
            idleDetection
            localFonts
            midi
            midiSysex
            nfc
            notifications
            paymentHandler
            periodicBackgroundSync
            protectedMediaIdentifier
            sensors
            storageAccess
            topLevelStorageAccess
            videoCapture
            videoCapturePanTiltZoom
            wakeLockScreen
            wakeLockSystem
            windowManagement
        """
        if not self.connection:
            raise RuntimeError("Browser not yet started. use await browser.start()")

        permissions = list(cdp.browser.PermissionType)
        permissions.remove(cdp.browser.PermissionType.CAPTURED_SURFACE_CONTROL)
        await self.connection.send(cdp.browser.grant_permissions(permissions))

    async def tile_windows(
        self, windows: List[tab.Tab] | None = None, max_columns: int = 0
    ) -> List[List[int]]:
        import math

        import mss

        m = mss.mss()
        screen, screen_width, screen_height = 3 * (None,)
        if m.monitors and len(m.monitors) >= 1:
            screen = m.monitors[0]
            screen_width = screen["width"]
            screen_height = screen["height"]
        if not screen or not screen_width or not screen_height:
            warnings.warn("no monitors detected")
            return []
        await self.update_targets()
        distinct_windows = defaultdict(list)

        if windows:
            tabs = windows
        else:
            tabs = self.tabs
        for tab_ in tabs:
            window_id, bounds = await tab_.get_window()
            distinct_windows[window_id].append(tab_)

        num_windows = len(distinct_windows)
        req_cols = max_columns or int(num_windows * (19 / 6))
        req_rows = int(num_windows / req_cols)

        while req_cols * req_rows < num_windows:
            req_rows += 1

        box_w = math.floor((screen_width / req_cols) - 1)
        box_h = math.floor(screen_height / req_rows)

        distinct_windows_iter = iter(distinct_windows.values())
        grid = []
        for x in range(req_cols):
            for y in range(req_rows):
                try:
                    tabs = next(distinct_windows_iter)
                except StopIteration:
                    continue
                if not tabs:
                    continue
                tab_ = tabs[0]

                try:
                    pos = [x * box_w, y * box_h, box_w, box_h]
                    grid.append(pos)
                    await tab_.set_window_size(*pos)
                except Exception:
                    logger.info(
                        "could not set window size. exception => ", exc_info=True
                    )
                    continue
        return grid

    async def _get_targets(self) -> List[cdp.target.TargetInfo]:
        if not self.connection:
            raise RuntimeError("Browser not yet started. use await browser.start()")
        info = await self.connection.send(cdp.target.get_targets(), _is_update=True)
        return info

    async def update_targets(self) -> None:
        targets: List[cdp.target.TargetInfo]
        targets = await self._get_targets()
        for t in targets:
            for existing_tab in self.targets:
                if existing_tab.target_id == t.target_id:
                    existing_tab.target.__dict__.update(t.__dict__)
                    break
            else:
                self.targets.append(
                    Connection(
                        (
                            f"ws://{self.config.host}:{self.config.port}"
                            f"/devtools/page"  # all types are 'page' somehow
                            f"/{t.target_id}"
                        ),
                        target=t,
                        _owner=self,
                    )
                )

        await asyncio.sleep(0)

    async def __aenter__(self) -> Browser:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: Any, exc_tb: Any
    ) -> None:
        if exc_type and exc_val:
            raise exc_type(exc_val)

    def __iter__(self) -> Browser:
        main_tab = self.main_tab
        if not main_tab:
            return self
        self._i = self.tabs.index(main_tab)
        return self

    def __reversed__(self) -> List[tab.Tab]:
        return list(reversed(list(self.tabs)))

    def __next__(self) -> tab.Tab:
        try:
            return self.tabs[self._i]
        except IndexError:
            del self._i
            raise StopIteration
        except AttributeError:
            del self._i
            raise StopIteration
        finally:
            if hasattr(self, "_i"):
                if self._i != len(self.tabs):
                    self._i += 1
                else:
                    del self._i

    async def stop(self) -> None:
        if not self.connection and not self._process:
            return

        if self.connection:
            await self.connection.send(cdp.browser.close())
            await self.connection.aclose()
            logger.debug("closed the connection")

        if self._process:
            try:
                self._process.terminate()
                logger.debug("gracefully stopping browser process")
                # wait 3 seconds for the browser to stop
                for _ in range(12):
                    if self._process.returncode is not None:
                        break
                    await asyncio.sleep(0.25)
                else:
                    logger.debug("browser process did not stop. killing it")
                    self._process.kill()
                    logger.debug("killed browser process")

                await asyncio.to_thread(self._process.wait)

            except ProcessLookupError:
                # ignore this well known race condition because it only means that
                # the process was not found while trying to terminate or kill it
                pass

            self._process = None
            self._process_pid = None

        await self._cleanup_temporary_profile()

    async def _cleanup_temporary_profile(self) -> None:
        if not self.config or self.config.uses_custom_data_dir:
            return

        for attempt in range(5):
            try:
                shutil.rmtree(self.config.user_data_dir, ignore_errors=False)
                logger.debug(
                    "successfully removed temp profile %s" % self.config.user_data_dir
                )
            except FileNotFoundError:
                break
            except (PermissionError, OSError) as e:
                if attempt == 4:
                    logger.debug(
                        "problem removing data dir %s\nConsider checking whether it's there and remove it by hand\nerror: %s",
                        self.config.user_data_dir,
                        e,
                    )
                await asyncio.sleep(0.15)
                continue

    def __del__(self) -> None:
        pass


class CookieJar:
    def __init__(self, browser: Browser):
        self._browser = browser
        # self._connection = connection

    async def get_all(
        self, requests_cookie_format: bool = False
    ) -> list[cdp.network.Cookie] | list[http.cookiejar.Cookie]:
        """
        get all cookies

        :param requests_cookie_format: when True, returns python http.cookiejar.Cookie objects, compatible  with requests library and many others.
        :type requests_cookie_format: bool
        :return:
        :rtype:

        """
        connection: Connection | None = None
        for tab_ in self._browser.tabs:
            if tab_.closed:
                continue
            connection = tab_
            break
        else:
            connection = self._browser.connection
        if not connection:
            raise RuntimeError("Browser not yet started. use await browser.start()")

        cookies = await connection.send(cdp.storage.get_cookies())
        if requests_cookie_format:
            import requests.cookies

            return [
                requests.cookies.create_cookie(  # type: ignore
                    name=c.name,
                    value=c.value,
                    domain=c.domain,
                    path=c.path,
                    expires=c.expires,
                    secure=c.secure,
                )
                for c in cookies
            ]
        return cookies

    async def set_all(self, cookies: List[cdp.network.CookieParam]) -> None:
        """
        set cookies

        :param cookies: list of cookies
        :type cookies:
        :return:
        :rtype:
        """
        connection: Connection | None = None
        for tab_ in self._browser.tabs:
            if tab_.closed:
                continue
            connection = tab_
            break
        else:
            connection = self._browser.connection
        if not connection:
            raise RuntimeError("Browser not yet started. use await browser.start()")

        await connection.send(cdp.storage.set_cookies(cookies))

    async def save(self, file: PathLike = ".session.dat", pattern: str = ".*") -> None:
        """
        save all cookies (or a subset, controlled by `pattern`) to a file to be restored later

        :param file:
        :type file:
        :param pattern: regex style pattern string.
               any cookie that has a  domain, key or value field which matches the pattern will be included.
               default = ".*"  (all)

               eg: the pattern "(cf|.com|nowsecure)" will include those cookies which:
                    - have a string "cf" (cloudflare)
                    - have ".com" in them, in either domain, key or value field.
                    - contain "nowsecure"
        :type pattern: str
        :return:
        :rtype:
        """
        compiled_pattern = re.compile(pattern)
        save_path = pathlib.Path(file).resolve()
        connection: Connection | None = None
        for tab_ in self._browser.tabs:
            if tab_.closed:
                continue
            connection = tab_
            break
        else:
            connection = self._browser.connection
        if not connection:
            raise RuntimeError("Browser not yet started. use await browser.start()")

        cookies: (
            list[cdp.network.Cookie] | list[http.cookiejar.Cookie]
        ) = await connection.send(cdp.storage.get_cookies())
        # if not connection:
        #     return
        # if not connection.websocket:
        #     return
        # if connection.websocket.closed:
        #     return
        cookies = await self.get_all(requests_cookie_format=False)
        included_cookies = []
        for cookie in cookies:
            for match in compiled_pattern.finditer(str(cookie.__dict__)):
                logger.debug(
                    "saved cookie for matching pattern '%s' => (%s: %s)",
                    compiled_pattern.pattern,
                    cookie.name,
                    cookie.value,
                )
                included_cookies.append(cookie)
                break
        pickle.dump(cookies, save_path.open("w+b"))

    async def load(self, file: PathLike = ".session.dat", pattern: str = ".*") -> None:
        """
        load all cookies (or a subset, controlled by `pattern`) from a file created by :py:meth:`~save_cookies`.

        :param file:
        :type file:
        :param pattern: regex style pattern string.
               any cookie that has a  domain, key or value field which matches the pattern will be included.
               default = ".*"  (all)

               eg: the pattern "(cf|.com|nowsecure)" will include those cookies which:
                    - have a string "cf" (cloudflare)
                    - have ".com" in them, in either domain, key or value field.
                    - contain "nowsecure"
        :type pattern: str
        :return:
        :rtype:
        """
        import re

        compiled_pattern = re.compile(pattern)
        save_path = pathlib.Path(file).resolve()
        cookies = pickle.load(save_path.open("r+b"))
        included_cookies = []
        for cookie in cookies:
            for match in compiled_pattern.finditer(str(cookie.__dict__)):
                included_cookies.append(cookie)
                logger.debug(
                    "loaded cookie for matching pattern '%s' => (%s: %s)",
                    compiled_pattern.pattern,
                    cookie.name,
                    cookie.value,
                )
                break
        await self.set_all(included_cookies)

    async def clear(self) -> None:
        """
        clear current cookies

        note: this includes all open tabs/windows for this browser

        :return:
        :rtype:
        """
        connection: Connection | None = None
        for tab_ in self._browser.tabs:
            if tab_.closed:
                continue
            connection = tab_
            break
        else:
            connection = self._browser.connection
        if not connection:
            raise RuntimeError("Browser not yet started. use await browser.start()")

        await connection.send(cdp.storage.clear_cookies())


class HTTPApi:
    def __init__(self, addr: Tuple[str, int]):
        self.host, self.port = addr
        self.api = "http://%s:%d" % (self.host, self.port)

    async def get(self, endpoint: str) -> Any:
        return await self._request(endpoint)

    async def post(self, endpoint: str, data: dict[str, str]) -> Any:
        return await self._request(endpoint, method="post", data=data)

    async def _request(
        self, endpoint: str, method: str = "get", data: dict[str, str] | None = None
    ) -> Any:
        url = urllib.parse.urljoin(
            self.api, f"json/{endpoint}" if endpoint else "/json"
        )
        if data and method.lower() == "get":
            raise ValueError("get requests cannot contain data")
        if not url:
            url = self.api + endpoint
        request = urllib.request.Request(url)
        request.method = method
        request.data = None
        if data:
            request.data = json.dumps(data).encode("utf-8")

        response = await asyncio.get_running_loop().run_in_executor(
            None, lambda: urllib.request.urlopen(request, timeout=10)
        )
        return json.loads(response.read())
