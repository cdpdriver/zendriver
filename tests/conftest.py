import asyncio
import logging
import os
import signal
import sys
import types
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from enum import Enum
from threading import Event
from types import FrameType

import pytest
import zendriver as zd


logger = logging.getLogger(__name__)


class BrowserMode(Enum):
    HEADLESS = 'headless'
    HEADFUL = 'headful'
    ALL = 'all'

    @property
    def fixture_params(self) -> list[dict[str, bool]]:
        if self == BrowserMode.HEADLESS:
            return [{'headless': True}]
        if self == BrowserMode.HEADFUL:
            return [{'headless': False}]
        if self == BrowserMode.ALL:
            return [{'headless': True}, {'headless': False}]
        return []


NEXT_TEST_EVENT = Event()


class TestConfig:
    BROWSER_MODE = BrowserMode(os.getenv('ZENDRIVER_TEST_BROWSERS', 'all'))
    PAUSE_AFTER_TEST = os.getenv('ZENDRIVER_PAUSE_AFTER_TEST', 'false') == 'true'
    SANDBOX = os.getenv('ZENDRIVER_TEST_SANDBOX', 'false') == 'true'
    USE_WAYLAND = os.getenv('WAYLAND_DISPLAY') is not None


class CreateBrowser(AbstractAsyncContextManager):  # type: ignore
    def __init__(
        self,
        *,
        headless: bool = True,
        sandbox: bool = TestConfig.SANDBOX,
        browser_args: list[str] | None = None,
        browser_connection_max_tries: int = 15,
        browser_connection_timeout: float = 3.0,
    ) -> None:
        args = []
        if not headless and TestConfig.USE_WAYLAND:
            # use wayland backend instead of x11
            args.extend(
                [
                    '--disable-features=UseOzonePlatform',
                    '--ozone-platform=wayland',
                ],
            )
        if browser_args is not None:
            args.extend(browser_args)

        self.config = zd.Config(
            headless=headless,
            sandbox=sandbox,
            browser_args=args,
            browser_connection_max_tries=browser_connection_max_tries,
            browser_connection_timeout=browser_connection_timeout,
        )

        self.browser: zd.Browser | None = None

    async def __aenter__(self) -> zd.Browser:
        self.browser = await zd.start(self.config)
        browser_pid = self.browser._process_pid
        assert browser_pid is not None and browser_pid > 0
        await self.browser.wait(0)
        return self.browser

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        if self.browser is not None and self.browser._process_pid is not None:
            await self.browser.stop()
            assert self.browser._process_pid is None


@pytest.fixture
def create_browser() -> type[CreateBrowser]:
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore

    return CreateBrowser


@pytest.fixture(params=TestConfig.BROWSER_MODE.fixture_params)
def headless(request: pytest.FixtureRequest) -> bool:
    return request.param['headless']


@pytest.fixture
async def browser(
    headless: bool,  # noqa: FBT001
    create_browser: type[CreateBrowser],
) -> AsyncGenerator[zd.Browser]:
    NEXT_TEST_EVENT.clear()

    async with create_browser(headless=headless) as browser:
        yield browser

    if TestConfig.PAUSE_AFTER_TEST:
        logger.info(
            'Pausing after test. Send next test hotkey (default Mod+Return) to continue to next test',
        )
        NEXT_TEST_EVENT.wait()


# signal handler for starting next test
def handle_next_test(signum: int, frame: FrameType | None) -> None:
    if not TestConfig.PAUSE_AFTER_TEST:
        logger.warning(
            'Next test signal received, but ZENDRIVER_PAUSE_AFTER_TEST is not set.',
        )
        logger.warning(
            'To enable pausing after each test, set ZENDRIVER_PAUSE_AFTER_TEST=true',
        )
        return

    NEXT_TEST_EVENT.set()


if hasattr(signal, 'SIGUSR1'):
    signal.signal(signal.SIGUSR1, handle_next_test)
else:
    logger.warning(
        'SIGUSR1 not available on this platform, handle_next_test will not be called.',
    )
