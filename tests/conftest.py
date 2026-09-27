import asyncio
import http.server
import logging
import os
import re
import signal
import sys
import threading
from contextlib import AbstractAsyncContextManager
from enum import Enum
from pathlib import Path
from threading import Event
from types import FrameType
from typing import AsyncGenerator, Any, Generator, Iterator

import pytest

import zendriver as zd

logger = logging.getLogger(__name__)


class BrowserMode(Enum):
    HEADLESS = "headless"
    HEADFUL = "headful"
    ALL = "all"

    @property
    def fixture_params(self) -> list[dict[str, bool]]:
        if self == BrowserMode.HEADLESS:
            return [{"headless": True}]
        elif self == BrowserMode.HEADFUL:
            return [{"headless": False}]
        elif self == BrowserMode.ALL:
            return [{"headless": True}, {"headless": False}]
        return []


NEXT_TEST_EVENT = Event()


class TestConfig:
    BROWSER_MODE = BrowserMode(os.getenv("ZENDRIVER_TEST_BROWSERS", "all"))
    PAUSE_AFTER_TEST = os.getenv("ZENDRIVER_PAUSE_AFTER_TEST", "false") == "true"
    SANDBOX = os.getenv("ZENDRIVER_TEST_SANDBOX", "false") == "true"
    USE_WAYLAND = os.getenv("WAYLAND_DISPLAY") is not None
    ARTIFACTS_DIR = Path(os.getenv("ZENDRIVER_TEST_ARTIFACTS_DIR", "test-artifacts"))


class CreateBrowser(AbstractAsyncContextManager[zd.Browser]):
    def __init__(
        self,
        *,
        headless: bool = True,
        sandbox: bool = TestConfig.SANDBOX,
        browser_args: list[str] | None = None,
        browser_connection_max_tries: int = 180,
        browser_connection_timeout: float = 0.25,
        lang: str | None = None,
    ):
        args = []
        if not headless and TestConfig.USE_WAYLAND:
            # use wayland backend instead of x11
            args.extend(
                ["--disable-features=UseOzonePlatform", "--ozone-platform=wayland"]
            )
        if browser_args is not None:
            args.extend(browser_args)

        self.config = zd.Config(
            headless=headless,
            sandbox=sandbox,
            browser_args=args,
            browser_connection_max_tries=browser_connection_max_tries,
            browser_connection_timeout=browser_connection_timeout,
            lang=lang,
        )

        self.browser: zd.Browser | None = None

    async def __aenter__(self) -> zd.Browser:
        self.browser = await zd.start(self.config)
        browser_pid = self.browser._process_pid
        assert browser_pid is not None and browser_pid > 0
        await self.browser.wait(0)
        return self.browser

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: Any, exc_tb: Any
    ) -> None:
        if self.browser is not None and self.browser._process_pid is not None:
            await self.browser.stop()
            assert self.browser._process_pid is None


@pytest.fixture
def create_browser() -> type[CreateBrowser]:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    return CreateBrowser


@pytest.fixture(params=TestConfig.BROWSER_MODE.fixture_params)
def headless(request: pytest.FixtureRequest) -> bool:
    return bool(request.param["headless"])


@pytest.fixture(scope="session")
async def shared_browsers() -> AsyncGenerator[dict[bool, zd.Browser], None]:
    browsers: dict[bool, zd.Browser] = {}
    yield browsers
    for browser in browsers.values():
        await browser.stop()


async def _get_shared_browser(
    browsers: dict[bool, zd.Browser], headless: bool
) -> zd.Browser:
    browser = browsers.get(headless)
    if browser is None or browser.stopped:
        browser = await CreateBrowser(headless=headless).__aenter__()
        browsers[headless] = browser
        return browser

    # closing the previous tabs also drops any handlers or overrides tests added to them
    new_tab = await browser.get("about:blank", new_tab=True)
    for tab in browser.tabs:
        if tab is not new_tab:
            await tab.close()
    await browser.cookies.clear()
    assert browser.tabs == [new_tab]
    return browser


TEST_REPORTS_KEY = pytest.StashKey[dict[str, pytest.TestReport]]()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    item.stash.setdefault(TEST_REPORTS_KEY, {})[report.when] = report
    return report


async def save_page_artifacts(
    request: pytest.FixtureRequest, browser: zd.Browser
) -> None:
    if not request.node.get_closest_marker("external") or browser.stopped:
        return
    report = request.node.stash.get(TEST_REPORTS_KEY, {}).get("call")
    if report is None or not report.failed:
        return

    directory = TestConfig.ARTIFACTS_DIR / re.sub(r"[^\w.-]", "_", request.node.nodeid)
    directory.mkdir(parents=True, exist_ok=True)
    for index, tab in enumerate(browser.tabs):
        try:
            (directory / f"tab-{index}.html").write_text(
                await tab.get_content(), encoding="utf-8"
            )
            await tab.save_screenshot(directory / f"tab-{index}.png", format="png")
            logger.info(
                "Saved artifacts for tab %d (%s) to %s", index, tab.url, directory
            )
        except Exception:
            logger.exception("Failed to save artifacts for tab %d (%s)", index, tab.url)


@pytest.fixture
def cross_site_iframe_url() -> Iterator[str]:
    """Serve a page on 127.0.0.1 embedding an iframe from localhost, which in turn
    embeds an iframe from 127.0.0.1 again.

    Each iframe is a different site than its parent, so Chrome's site isolation
    puts it in another process and exposes it as a separate "iframe" target.
    """

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            port = server.server_address[1]
            if self.path == "/child":
                body = (
                    "<html><body>"
                    "<p id='child'>hello from iframe</p>"
                    "<button id='button' onclick=\"this.innerText='clicked'\">"
                    "click me</button>"
                    f"<iframe id='grandchild-frame' src='http://127.0.0.1:{port}/grandchild'></iframe>"
                    "</body></html>"
                )
            elif self.path == "/grandchild":
                body = (
                    "<html><body><p id='grandchild'>hello from nested iframe</p>"
                    "</body></html>"
                )
            else:
                body = (
                    "<html><body>"
                    f"<iframe id='child-frame' src='http://localhost:{port}/child'></iframe>"
                    "</body></html>"
                )
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
async def browser(
    request: pytest.FixtureRequest,
    headless: bool,
    create_browser: type[CreateBrowser],
    shared_browsers: dict[bool, zd.Browser],
) -> AsyncGenerator[zd.Browser, None]:
    NEXT_TEST_EVENT.clear()

    if request.node.get_closest_marker("fresh_browser"):
        async with create_browser(headless=headless) as browser:
            yield browser
            await save_page_artifacts(request, browser)
    else:
        browser = await _get_shared_browser(shared_browsers, headless)
        yield browser
        await save_page_artifacts(request, browser)

    if TestConfig.PAUSE_AFTER_TEST:
        logger.info(
            "Pausing after test. Send next test hotkey (default Mod+Return) to continue to next test"
        )
        NEXT_TEST_EVENT.wait()


# signal handler for starting next test
def handle_next_test(signum: int, frame: FrameType | None) -> None:
    if not TestConfig.PAUSE_AFTER_TEST:
        logger.warning(
            "Next test signal received, but ZENDRIVER_PAUSE_AFTER_TEST is not set."
        )
        logger.warning(
            "To enable pausing after each test, set ZENDRIVER_PAUSE_AFTER_TEST=true"
        )
        return

    NEXT_TEST_EVENT.set()


if hasattr(signal, "SIGUSR1"):
    signal.signal(signal.SIGUSR1, handle_next_test)
else:
    logger.warning(
        "SIGUSR1 not available on this platform, handle_next_test will not be called."
    )
