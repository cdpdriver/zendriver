from __future__ import annotations

import asyncio
import copy
import json
import logging
import pathlib
import pickle
import re
import shutil
import urllib.parse
import urllib.request
import warnings
from collections import defaultdict
from collections.abc import Iterator, Reversible
from textwrap import dedent
from typing import (
    TYPE_CHECKING,
    Any,
    Self,
)

import asyncio_atexit

from .. import cdp
from . import tab, util
from ._contradict import ContraDict
from .config import Config, is_posix
from .connection import Connection


if TYPE_CHECKING:
    import http.cookiejar
    import subprocess
    import types

    from .config import BrowserType, PathLike

logger = logging.getLogger(__name__)


class Browser(Reversible[tab.Tab], Iterator[tab.Tab]):
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
        browser: BrowserType = 'auto',
        browser_args: list[str] | None = None,
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

    def __init__(self, config: Config) -> None:
        """
        constructor. to create a instance, use :py:meth:`Browser.create(...)`

        :param config:
        """

        try:
            asyncio.get_running_loop()
        except RuntimeError as err:
            raise RuntimeError(
                f'{self.__class__.__name__} objects of this class are created using await {self.__class__.__name__}.create()',
            ) from err
        # weakref.finalize(self, self._quit, self)

        # each instance gets it's own copy so this class gets a copy that it can
        # use to help manage the browser instance data (needed for multiple browsers)
        self.config = copy.deepcopy(config)

        self.targets: list[Connection] = []
        """current targets (all types)"""
        self.info: ContraDict | None = None
        self._target = None
        self._process = None
        self._process_pid = None
        self._is_updating = asyncio.Event()
        self.connection = None
        logger.debug('Session object initialized: %s', vars(self))

    @property
    def websocket_url(self) -> str:
        if not self.info:
            msg = 'Browser not yet started. use await browser.start()'
            raise RuntimeError(msg)

        return self.info.webSocketDebuggerUrl  # type: ignore

    @property
    def main_tab(self) -> tab.Tab:
        """returns the target which was launched with the browser"""

        if not self.tabs:
            msg = 'Could not find any tabs'
            raise ValueError(msg)

        return self.tabs[0]

    @property
    def tabs(self) -> list[tab.Tab]:
        """returns the current targets which are of type "page"
        :return:
        """
        return [t for t in self.targets if (t.type_ == 'page') and isinstance(t, tab.Tab)]

    @property
    def cookies(self) -> CookieJar:
        if not self._cookies:
            self._cookies = CookieJar(self)
        return self._cookies

    @property
    def stopped(self) -> bool:
        return not (self._process and self._process.poll() is None)

    async def wait(self, time: float = 1) -> Browser:
        """wait for <time> seconds. important to use, especially in between page navigation

        :param time:
        :return:
        """
        return await asyncio.sleep(time, result=self)

    sleep = wait
    """alias for wait"""

    async def _handle_target_info_changed(self, event: cdp.target.TargetInfoChanged) -> None:
        """this is an internal handler which updates the targets when chrome emits the corresponding event"""

        if not isinstance(event, cdp.target.TargetInfoChanged):
            logger.error('Unexpected event type for target handler %s', type(event))
            return

        async with self._update_target_info_mutex:
            target_info = event.target_info

            current_tab = self.get_target_by_id(tab.Tab, target_info.target_id)
            if not current_tab:
                logger.error('Could not get tab from targetID')
                return

            current_target = current_tab.target

            if logger.getEffectiveLevel() <= 10:
                changes = util.compare_target_info(current_target, target_info)
                changes_string = ''
                for change in changes:
                    key, old, new = change
                    changes_string += f'\n{key}: {old} => {new}\n'
                logger.debug('target #%d has changed: %s', self.targets.index(current_tab), changes_string)

            current_tab.target = target_info

    async def _handle_target_created(self, event: cdp.target.TargetCreated) -> None:
        """this is an internal handler which updates the targets when chrome emits the corresponding event"""

        if not isinstance(event, cdp.target.TargetCreated):
            logger.error('Unexpected event type for target handler %s', type(event))
            return

        async with self._update_target_info_mutex:
            target_info = event.target_info
            from .tab import Tab

            new_target = Tab(
                (
                    f'ws://{self.config.host}:{self.config.port}'
                    f'/devtools/{target_info.type_ or "page"}'  # all types are 'page' internally in chrome apparently
                    f'/{target_info.target_id}'
                ),
                target=target_info,
                browser=self,
            )

            self.targets.append(new_target)

            logger.debug('target #%d created => %s', len(self.targets), new_target)

    async def _handle_target_destroyed(self, event: cdp.target.TargetDestroyed) -> None:
        """this is an internal handler which updates the targets when chrome emits the corresponding event"""

        if not isinstance(event, cdp.target.TargetDestroyed):
            logger.error('Unexpected event type for target handler %s', type(event))
            return

        async with self._update_target_info_mutex:
            current_tab = self.get_target_by_id(tab.Tab, event.target_id)
            if not current_tab:
                logger.error('Could not get tab from targetID')
                return

            logger.debug('target removed. id # %d => %s', self.targets.index(current_tab), current_tab)
            self.targets.remove(current_tab)

    async def _handle_target_crashed(self, event: cdp.target.TargetCrashed) -> None:
        """this is an internal handler which updates the targets when chrome emits the corresponding event"""

        if not isinstance(event, cdp.target.TargetCrashed):
            logger.error('Unexpected event type for target handler %s', type(event))
            return

        async with self._update_target_info_mutex:
            current_tab = self.get_target_by_id(tab.Tab, event.target_id)
            if not current_tab:
                logger.error('Target ID %s crashed.', event.target_id)
                logger.error('Could not get tab from targetID')
                return

            logger.error('Target %s crashed.', current_tab)

            logger.debug('target removed. id # %d => %s', self.targets.index(current_tab), current_tab)
            self.targets.remove(current_tab)

    def get_target_by_id[T: Connection](
        self,
        target_type: type[T],
        target_id: cdp.target.TargetID,
    ) -> T | None:
        connection = [t for t in self.targets if t.type_ == 'page' and t.target_id == target_id]
        if not connection:
            return None
        target = connection[0]
        if not isinstance(target, target_type):
            raise TypeError(target)
        return target

    async def get(
        self,
        url: str = 'about:blank',
        *,
        new_tab: bool = False,
        new_window: bool = False,
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
            msg = 'Browser not yet started. use await browser.start()'
            raise RuntimeError(msg)

        future = asyncio.get_running_loop().create_future()
        event_type = cdp.target.TargetInfoChanged

        async def get_handler(event: cdp.target.TargetInfoChanged) -> None:  # noqa: RUF029
            if future.done():
                return

            # ignore TargetInfoChanged event from browser startup
            if event.target_info.url != 'about:blank' or (
                url == 'about:blank' and event.target_info.url == 'about:blank'
            ):
                future.set_result(event)

        self.connection.add_handler(event_type, get_handler)

        if new_tab or new_window:
            # create new target using the browser session
            target_id = await self.connection.send(
                cdp.target.create_target(
                    url,
                    new_window=new_window,
                    enable_begin_frame_control=True,
                ),
            )
            # get the connection matching the new target_id from our inventory
            connection = self.get_target_by_id(tab.Tab, target_id)
            if not connection:
                raise ValueError(connection)

            connection.browser = self
        else:
            # first tab from browser.tabs
            connection = self.tabs[0]
            # use the tab to navigate to new url
            await connection.send(cdp.page.navigate(url))
            connection.browser = self

        await asyncio.wait_for(future, 10)
        self.connection.remove_handlers(event_type, get_handler)

        return connection

    async def start(self) -> Browser:
        """launches the actual browser"""
        if not self:
            msg = 'Cannot be called as a class method. Use `await Browser.create()` to create a new instance'
            raise ValueError(msg)

        if self._process or self._process_pid:
            if self._process and self._process.returncode is not None:
                return await self.create(config=self.config)
            warnings.warn('ignored! this call has no effect when already running.', stacklevel=1)
            return self

        connect_existing = False
        if self.config.host is not None and self.config.port is not None:
            connect_existing = True
        else:
            self.config.host = '127.0.0.1'
            self.config.port = util.free_port()

        if not connect_existing:
            logger.debug(
                'BROWSER EXECUTABLE PATH: %s',
                self.config.browser_executable_path,
            )
            if not pathlib.Path(self.config.browser_executable_path).exists():  # noqa: ASYNC240
                msg = dedent(
                    """
                    ---------------------
                    Could not determine browser executable.
                    ---------------------
                    Make sure your browser is installed in the default location (path).
                    If you are sure about the browser executable, you can specify it using
                    the `browser_executable_path='{}` parameter.
                    """.format(
                        '/path/to/browser/executable' if is_posix else 'c:/path/to/your/browser.exe',
                    ),
                )
                raise FileNotFoundError(
                    msg,
                )

        if getattr(self.config, '_extensions', None):
            self.config.add_argument(f'--load-extension={",".join(str(_) for _ in self.config._extensions)}')

        if self.config.lang is not None:
            self.config.add_argument(f'--lang={self.config.lang}')

        exe = self.config.browser_executable_path
        params = self.config()
        params.append('about:blank')

        logger.info(
            'starting\n\texecutable :%s\n\narguments:\n%s',
            exe,
            '\n\t'.join(params),
        )
        if not connect_existing:
            self._process = util._start_process(exe, params, is_posix=is_posix)
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
                    'Browser stderr: %s',
                    stderr or 'No output from browser',
                )

            await self.stop()
            msg = """
                ---------------------
                Failed to connect to browser
                ---------------------
                One of the causes could be when you are running as root.
                In that case you need to pass no_sandbox=True
                """
            raise Exception(msg)

        self.connection = Connection(self.info.webSocketDebuggerUrl, _owner=self)

        if self.config.autodiscover_targets:
            logger.info('enabling autodiscover targets')

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
                self._handle_target_info_changed,
            ]
            self.connection.handlers[cdp.target.TargetCreated] = [
                self._handle_target_created,
            ]
            self.connection.handlers[cdp.target.TargetDestroyed] = [
                self._handle_target_destroyed,
            ]
            self.connection.handlers[cdp.target.TargetCrashed] = [
                self._handle_target_crashed,
            ]
            await self.connection.send(cdp.target.set_discover_targets(discover=True))
        await self.update_targets()
        return self

    async def test_connection(self) -> bool:
        if not self._http:
            msg = 'HTTPApi not yet initialized'
            raise ValueError(msg)

        try:
            self.info = ContraDict(await self._http.get('version'), silent=True)
        except Exception:
            logger.debug('Could not start', exc_info=True)
            return False
        else:
            return True

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
            msg = 'Browser not yet started. use await browser.start()'
            raise RuntimeError(msg)

        permissions = list(cdp.browser.PermissionType)
        permissions.remove(cdp.browser.PermissionType.CAPTURED_SURFACE_CONTROL)
        await self.connection.send(cdp.browser.grant_permissions(permissions))

    async def tile_windows(
        self,
        windows: list[tab.Tab] | None = None,
        max_columns: int = 0,
    ) -> list[list[int]]:
        import math

        import mss

        m = mss.mss()
        screen, screen_width, screen_height = 3 * (None,)
        if m.monitors and len(m.monitors) >= 1:
            screen = m.monitors[0]
            screen_width = screen['width']
            screen_height = screen['height']
        if not screen or not screen_width or not screen_height:
            warnings.warn('no monitors detected', stacklevel=1)
            return []
        await self.update_targets()
        distinct_windows = defaultdict(list)

        tabs = windows or self.tabs
        for tab_ in tabs:
            window_id, _bounds = await tab_.get_window()
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
                        'could not set window size. exception => ',
                        exc_info=True,
                    )
                    continue
        return grid

    async def _get_targets(self) -> list[cdp.target.TargetInfo]:
        if not self.connection:
            msg = 'Browser not yet started. use await browser.start()'
            raise RuntimeError(msg)
        return await self.connection.send(cdp.target.get_targets(), _is_update=True)

    async def update_targets(self) -> None:
        targets = await self._get_targets()
        async with self._update_target_info_mutex:
            for target_info in targets:
                for existing_tab in self.targets:
                    if existing_tab.target_id == target_info.target_id:
                        existing_tab.target.__dict__.update(target_info.__dict__)
                        break
                else:
                    new_target = tab.Tab(
                        (
                            f'ws://{self.config.host}:{self.config.port}'
                            f'/devtools/{target_info.type_ or "page"}'  # all types are 'page' internally in chrome apparently
                            f'/{target_info.target_id}'
                        ),
                        target=target_info,
                        browser=self,
                    )

                    self.targets.append(new_target)

        await asyncio.sleep(0)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        if exc_type and exc_val:
            raise exc_type(exc_val)

    def __iter__(self) -> Browser:
        main_tab = self.main_tab
        if not main_tab:
            return self
        self._i = self.tabs.index(main_tab)
        return self

    def __reversed__(self) -> Iterator[tab.Tab]:
        return reversed(self.tabs)

    def __next__(self) -> tab.Tab:
        try:
            return self.tabs[self._i]
        except IndexError:
            del self._i
            raise StopIteration from None
        except AttributeError:
            del self._i
            raise StopIteration from None
        finally:
            if hasattr(self, '_i'):
                if self._i < len(self.tabs):
                    self._i += 1
                else:
                    del self._i

    async def stop(self) -> None:
        if not self.connection and not self._process:
            return

        if self.connection:
            try:
                await self.connection.send(cdp.browser.close())
            except Exception:
                logger.warning(
                    'Could not send the close command when stopping the browser. Likely the browser is already gone. Closing the connection.',
                )
            await self.connection.aclose()
            logger.debug('closed the connection')

        if self._process:
            try:
                self._process.terminate()
                logger.debug('gracefully stopping browser process')
                # wait 3 seconds for the browser to stop
                for _ in range(12):
                    if self._process.poll() is not None:
                        break
                    await asyncio.sleep(0.25)
                else:
                    logger.warning('browser process did not stop. killing it')
                    self._process.kill()
                    logger.warning('killed browser process')

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
                logger.debug('successfully removed temp profile %s', self.config.user_data_dir)

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
    def __init__(self, browser: Browser) -> None:
        self._browser = browser
        # self._connection = connection

    async def get_all(
        self,
        *,
        requests_cookie_format: bool = False,
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
            msg = 'Browser not yet started. use await browser.start()'
            raise RuntimeError(msg)

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

    async def set_all(self, cookies: list[cdp.network.CookieParam]) -> None:
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
            msg = 'Browser not yet started. use await browser.start()'
            raise RuntimeError(msg)

        await connection.send(cdp.storage.set_cookies(cookies))

    async def save(self, file: PathLike = '.session.dat', pattern: str = '.*') -> None:
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
        save_path = pathlib.Path(file).resolve()  # noqa: ASYNC240
        connection: Connection | None = None
        for tab_ in self._browser.tabs:
            if tab_.closed:
                continue
            connection = tab_
            break
        else:
            connection = self._browser.connection
        if not connection:
            msg = 'Browser not yet started. use await browser.start()'
            raise RuntimeError(msg)

        cookies: list[cdp.network.Cookie] | list[http.cookiejar.Cookie] = await connection.send(
            cdp.storage.get_cookies(),
        )
        # if not connection:
        #     return
        # if not connection.websocket:
        #     return
        # if connection.websocket.closed:
        #     return
        cookies = await self.get_all(requests_cookie_format=False)
        included_cookies = []
        for cookie in cookies:
            for _match in compiled_pattern.finditer(str(cookie.__dict__)):
                logger.debug(
                    "saved cookie for matching pattern '%s' => (%s: %s)",
                    compiled_pattern.pattern,
                    cookie.name,
                    cookie.value,
                )
                included_cookies.append(cookie)
                break
        pickle.dump(cookies, save_path.open('w+b'))

    async def load(self, file: PathLike = '.session.dat', pattern: str = '.*') -> None:
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
        save_path = pathlib.Path(file).resolve()  # noqa: ASYNC240
        cookies = pickle.load(save_path.open('r+b'))
        included_cookies = []
        for cookie in cookies:
            for _match in compiled_pattern.finditer(str(cookie.__dict__)):
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
            msg = 'Browser not yet started. use await browser.start()'
            raise RuntimeError(msg)

        await connection.send(cdp.storage.clear_cookies())


class HTTPApi:
    def __init__(self, addr: tuple[str, int]) -> None:
        self.host, self.port = addr
        self.api = f'http://{self.host}:{self.port}'

    async def get(self, endpoint: str) -> Any:
        return await self._request(endpoint)

    async def post(self, endpoint: str, data: dict[str, str]) -> Any:
        return await self._request(endpoint, method='post', data=data)

    async def _request(
        self,
        endpoint: str,
        method: str = 'get',
        data: dict[str, str] | None = None,
    ) -> Any:
        url = urllib.parse.urljoin(
            self.api,
            f'json/{endpoint}' if endpoint else '/json',
        )
        if data and method.lower() == 'get':
            msg = 'get requests cannot contain data'
            raise ValueError(msg)
        if not url:
            url = self.api + endpoint
        request = urllib.request.Request(url)  # noqa: S310
        request.method = method
        request.data = None
        if data:
            request.data = json.dumps(data).encode('utf-8')

        response = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: urllib.request.urlopen(request, timeout=10),  # noqa: ASYNC210, S310
        )
        return json.loads(response.read())
