import asyncio

import zendriver as zd


async def get_frames(tab: zd.Tab, count: int) -> list[zd.Tab]:
    frames: list[zd.Tab] = []
    for _ in range(50):
        frames = await tab.get_frames()
        if len(frames) >= count:
            return frames
        await asyncio.sleep(0.1)
    raise AssertionError(f"expected {count} frames, found {len(frames)}")


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


async def test_get_frames_returns_nested_cross_site_frames(
    browser: zd.Browser, cross_site_iframe_url: str
) -> None:
    tab = await browser.get(cross_site_iframe_url)

    frames = await get_frames(tab, 2)
    child = next(frame for frame in frames if (frame.url or "").endswith("/child"))
    grandchild = next(
        frame for frame in frames if (frame.url or "").endswith("/grandchild")
    )
    await child.select("#child")
    await grandchild.select("#grandchild")

    assert (
        await child.evaluate("document.getElementById('child').innerText")
        == "hello from iframe"
    )
    assert (
        await grandchild.evaluate("document.getElementById('grandchild').innerText")
        == "hello from nested iframe"
    )


async def test_select_with_include_frames_clicks_element_in_cross_site_frame(
    browser: zd.Browser, cross_site_iframe_url: str
) -> None:
    tab = await browser.get(cross_site_iframe_url)

    button = await tab.select("#button", include_frames=True)
    await button.mouse_click()

    for _ in range(50):
        text = await button.tab.evaluate("document.getElementById('button').innerText")
        if text == "clicked":
            break
        await asyncio.sleep(0.1)
    assert text == "clicked"


async def test_select_all_with_include_frames_searches_nested_cross_site_frames(
    browser: zd.Browser, cross_site_iframe_url: str
) -> None:
    tab = await browser.get(cross_site_iframe_url)
    await tab.select("#grandchild", include_frames=True)

    paragraphs = await tab.select_all("p", include_frames=True)

    assert sorted(str(p.get("id")) for p in paragraphs) == ["child", "grandchild"]


async def test_find_with_include_frames_searches_cross_site_frames(
    browser: zd.Browser, cross_site_iframe_url: str
) -> None:
    tab = await browser.get(cross_site_iframe_url)

    paragraph = await tab.find("hello from nested iframe", include_frames=True)

    assert paragraph.get("id") == "grandchild"
    assert paragraph.tab.type_ == "iframe"


async def test_element_get_frame_returns_frame_of_cross_site_iframe(
    browser: zd.Browser, cross_site_iframe_url: str
) -> None:
    tab = await browser.get(cross_site_iframe_url)
    iframe = await tab.select("#child-frame")

    frame = None
    for _ in range(50):
        frame = await iframe.get_frame()
        if frame is not None:
            break
        await asyncio.sleep(0.1)

    assert frame is not None
    await frame.select("#child")
    assert (
        await frame.evaluate("document.getElementById('child').innerText")
        == "hello from iframe"
    )
