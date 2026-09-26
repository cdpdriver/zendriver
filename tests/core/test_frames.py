import asyncio

import zendriver as zd


async def test_tab_uses_session_on_browser_websocket(browser: zd.Browser) -> None:
    tab = await browser.get("about:blank")

    assert await tab.evaluate("1 + 1") == 2
    assert tab.session_id is not None
    assert browser.connection is not None
    assert tab.websocket is browser.connection.websocket


async def test_tab_session_is_detached_when_tab_closes(browser: zd.Browser) -> None:
    tab = await browser.get("about:blank", new_tab=True)
    await tab.evaluate("1 + 1")

    await tab.close()
    for _ in range(50):
        if tab.closed:
            break
        await asyncio.sleep(0.1)

    assert tab.closed
    assert tab.session_id is None
