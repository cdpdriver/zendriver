import pytest
from psutil import Process
from pytest_mock import MockerFixture

import zendriver as zd
from tests.conftest import CreateBrowser
from zendriver import cdp


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
    page = await browser.get("https://example.com")
    content = await page.get_content()
    assert content.lower().startswith("<!doctype html>")


async def test_update_target_sets_target_title(browser: zd.Browser) -> None:
    page = await browser.get("https://example.com")
    await page.update_target()
    assert page.target
    assert page.target.title == "Example Domain"


async def test_browser_stop_can_be_called_on_a_closed_connection(
    browser: zd.Browser,
) -> None:
    await browser.get("https://example.com")

    assert browser.connection is not None
    assert not browser.connection.closed

    await browser.connection.aclose()

    assert browser.connection.closed

    await browser.stop()
    assert browser.stopped


async def test_browser_stop_can_be_called_multiple_times(browser: zd.Browser) -> None:
    await browser.get("https://example.com")

    await browser.stop()
    assert browser.stopped

    await browser.stop()
    assert browser.stopped


async def test_browser_stopped_is_true_after_calling_stop(browser: zd.Browser) -> None:
    await browser.get("https://example.com")
    await browser.stop()
    assert browser.stopped


async def test_browser_stopped_is_true_when_stopped_externally(
    browser: zd.Browser,
) -> None:
    await browser.get("https://example.com")
    await browser.sleep(2)
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
        except TimeoutError:
            continue

    assert not psproc.is_running()
    assert browser.stopped

    await browser.stop()
