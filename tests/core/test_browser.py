import asyncio
import gc
import http.cookiejar
import pathlib
import pickle
import subprocess
import weakref

import psutil
import pytest
from psutil import Process
from pytest_mock import MockerFixture

import zendriver as zd
from tests.conftest import CreateBrowser
from tests.sample_data import sample_file
from zendriver import cdp
from zendriver.core.connection import ProtocolException

# these tests exercise the browser lifecycle (e.g. stopping it)
pytestmark = pytest.mark.fresh_browser


async def test_connection_error_raises_exception_and_logs_stderr(
    create_browser: type[CreateBrowser],
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mocker.patch(
        "zendriver.core.browser.Browser.test_connection",
        return_value=False,
    )
    with caplog.at_level("INFO"):
        with pytest.raises(Exception):
            async with create_browser(
                browser_connection_max_tries=1, browser_connection_timeout=0.1
            ) as _:
                pass
    assert "Browser stderr" in caplog.text


async def test_get_content_gets_html_content(browser: zd.Browser) -> None:
    page = await browser.get(sample_file("groceries.html"))
    content = await page.get_content()
    assert content.lower().startswith("<!doctype html>")


async def test_update_target_sets_target_title(browser: zd.Browser) -> None:
    page = await browser.get(sample_file("groceries.html"))
    await page.wait_for_ready_state("complete")
    await page.update_target()
    assert page.target
    assert page.target.title == "Grocery List"


async def test_browser_stop_can_be_called_on_a_closed_connection(
    browser: zd.Browser,
) -> None:
    await browser.get(sample_file("groceries.html"))

    assert browser.connection is not None
    assert not browser.connection.closed

    await browser.connection.aclose()

    assert browser.connection.closed

    await browser.stop()
    assert browser.stopped


async def test_browser_stop_can_be_called_multiple_times(browser: zd.Browser) -> None:
    await browser.get(sample_file("groceries.html"))

    await browser.stop()
    assert browser.stopped

    await browser.stop()
    assert browser.stopped


async def test_browser_stop_exits_gracefully_without_kill(
    browser: zd.Browser, mocker: MockerFixture
) -> None:
    assert browser._process is not None
    kill = mocker.spy(browser._process, "kill")

    loop = asyncio.get_running_loop()
    start = loop.time()
    await browser.stop()
    elapsed = loop.time() - start

    assert browser.stopped
    kill.assert_not_called()
    assert elapsed < 2


async def test_browser_is_garbage_collected_after_stop(
    create_browser: type[CreateBrowser],
) -> None:
    browser = await zd.start(create_browser().config)
    await browser.get(sample_file("groceries.html"))
    await browser.stop()

    browser_ref = weakref.ref(browser)
    del browser
    gc.collect()

    assert browser_ref() is None


async def test_browser_stopped_is_true_after_calling_stop(browser: zd.Browser) -> None:
    await browser.get(sample_file("groceries.html"))
    await browser.stop()
    assert browser.stopped


async def test_browser_stopped_is_true_when_stopped_externally(
    browser: zd.Browser,
) -> None:
    await browser.get(sample_file("groceries.html"))
    assert not browser.stopped
    process = browser._process
    process_id = browser._process_pid

    # Check that we got the browser process info.
    assert process
    assert process_id

    psproc = Process(process_id)

    if browser.connection:
        # Stop the browser without using browser.stop() function to emulate a headful browser being closed by the user."
        await browser.connection.send(cdp.browser.close())
        await browser.connection.aclose()

    wait_attempts = 100
    wait_timeout = 0.2

    # "Wait up to {wait_timeout * wait_attempts} seconds for the process to terminate"
    for _ in range(wait_attempts):
        if not psproc.is_running():
            break
        try:
            psproc.wait(wait_timeout)
        except (TimeoutError, subprocess.TimeoutExpired, psutil.TimeoutExpired):
            # So many different exceptions... Why lib authors, why?
            continue

    assert not psproc.is_running()
    assert browser.stopped

    await browser.stop()


async def test_cookies_save_writes_only_the_cookies_matching_the_pattern(
    browser: zd.Browser,
    tmp_path: pathlib.Path,
) -> None:
    await browser.cookies.set_all(
        [
            cdp.network.CookieParam(
                name="wanted", value="nowsecure", domain="example.com", path="/"
            ),
            cdp.network.CookieParam(
                name="ignored", value="somethingelse", domain="example.com", path="/"
            ),
        ]
    )

    save_file = tmp_path / "cookies.dat"
    await browser.cookies.save(save_file, pattern="nowsecure")

    with save_file.open("rb") as f:
        saved = pickle.load(f)

    assert [cookie.name for cookie in saved] == ["wanted"]


async def test_cookies_save_and_load_round_trip(
    browser: zd.Browser,
    tmp_path: pathlib.Path,
) -> None:
    await browser.cookies.set_all(
        [
            cdp.network.CookieParam(
                name="kept", value="yes", domain="example.com", path="/"
            )
        ]
    )

    save_file = tmp_path / "cookies.dat"
    await browser.cookies.save(save_file)

    await browser.cookies.clear()
    assert await browser.cookies.get_all() == []

    await browser.cookies.load(save_file)

    restored = {cookie.name: cookie.value for cookie in await browser.cookies.get_all()}
    assert restored.get("kept") == "yes"


async def test_cookies_get_all_in_requests_cookie_format(
    browser: zd.Browser,
) -> None:
    await browser.cookies.set_all(
        [
            cdp.network.CookieParam(
                name="session_cookie",
                value="yes",
                domain="example.com",
                path="/",
                http_only=True,
            ),
            cdp.network.CookieParam(
                name="persistent_cookie",
                value="yes",
                domain="example.com",
                path="/",
                expires=cdp.network.TimeSinceEpoch(4102444800),
            ),
        ]
    )

    cookies = {
        cookie.name: cookie
        for cookie in await browser.cookies.get_all(requests_cookie_format=True)
    }

    session_cookie = cookies["session_cookie"]
    assert isinstance(session_cookie, http.cookiejar.Cookie)
    assert session_cookie.expires is None
    assert not session_cookie.is_expired()
    assert session_cookie.has_nonstandard_attr("HttpOnly")
    assert cookies["persistent_cookie"].expires is not None
    assert not cookies["persistent_cookie"].is_expired()
    assert not cookies["persistent_cookie"].has_nonstandard_attr("HttpOnly")


async def test_browser_starts_with_lang_option(
    create_browser: type[CreateBrowser],
) -> None:
    """Setting `lang` used to raise ValueError from Browser.start (#262)."""
    async with create_browser(lang="de-DE") as browser:
        assert "--lang=de-DE" in browser.config()
        page = await browser.get("about:blank")
        assert await page.evaluate("1 + 1") == 2


async def test_iframe_target_can_be_connected_to(
    browser: zd.Browser, cross_site_iframe_url: str
) -> None:
    """Connecting to iframe targets used to fail with a 404 (#275)."""
    await browser.get(cross_site_iframe_url)

    iframe_target = None
    for _ in range(50):
        iframe_target = next(
            (
                t
                for t in browser.targets
                if isinstance(t, zd.Tab) and t.type_ == "iframe"
            ),
            None,
        )
        if iframe_target is not None:
            break
        await asyncio.sleep(0.1)

    assert iframe_target is not None, "no iframe target was discovered"
    assert iframe_target.websocket_url.endswith(
        f"/devtools/page/{iframe_target.target_id}"
    )

    await iframe_target.select("#child")
    text = await iframe_target.evaluate("document.getElementById('child').innerText")
    assert text == "hello from iframe"


async def test_start_waits_for_initial_tab(
    create_browser: type[CreateBrowser], mocker: MockerFixture, headless: bool
) -> None:
    get_targets = zd.Browser._get_targets
    calls = 0

    async def get_targets_without_initial_tab(
        self: zd.Browser,
    ) -> list[cdp.target.TargetInfo]:
        nonlocal calls
        calls += 1
        targets = await get_targets(self)
        return targets if calls > 1 else [t for t in targets if t.type_ != "page"]

    mocker.patch.object(zd.Browser, "_get_targets", get_targets_without_initial_tab)
    browser_context = create_browser(headless=headless)
    browser_context.config.autodiscover_targets = False
    async with browser_context as browser:
        assert len(browser.tabs) == 1


async def test_pending_commands_fail_when_browser_process_dies(
    browser: zd.Browser,
) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    assert browser.connection is not None
    assert browser._process_pid is not None

    process = Process(browser._process_pid)
    process.suspend()
    browser_command = asyncio.create_task(
        browser.connection.send(cdp.browser.get_version())
    )
    tab_command = asyncio.create_task(tab.send(cdp.page.get_frame_tree()))
    await asyncio.sleep(0.5)
    assert not browser_command.done()
    assert not tab_command.done()

    process.kill()
    results = await asyncio.wait_for(
        asyncio.gather(browser_command, tab_command, return_exceptions=True),
        timeout=10,
    )

    assert all(isinstance(result, Exception) for result in results)


async def test_pending_commands_fail_when_connection_is_closed(
    browser: zd.Browser,
) -> None:
    await browser.get(sample_file("groceries.html"))
    assert browser.connection is not None
    assert browser._process_pid is not None

    process = Process(browser._process_pid)
    process.suspend()
    try:
        browser_command = asyncio.create_task(
            browser.connection.send(cdp.browser.get_version())
        )
        await asyncio.sleep(0.5)
        assert not browser_command.done()

        await browser.connection.aclose()

        with pytest.raises(ProtocolException):
            await asyncio.wait_for(browser_command, timeout=10)
    finally:
        process.resume()


async def test_get_tab_matches_url_and_title(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    await tab.wait_for_ready_state("complete")

    assert await browser.get_tab("groceries.html") is tab
    assert await browser.get_tab("grocery list") is tab
    assert await browser.get_tab("does-not-exist") is None
