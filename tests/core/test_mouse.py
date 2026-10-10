from typing import Any

import zendriver as zd
from tests.sample_data import sample_file


async def open_mouse_events_page(browser: zd.Browser) -> zd.Tab:
    tab = await browser.get(sample_file("mouse_events.html"))
    await tab.wait_for_ready_state("complete")
    return tab


async def get_mouse_events(tab: zd.Tab) -> list[dict[str, Any]]:
    events = await tab.evaluate("window.mouseEvents")
    assert isinstance(events, list)
    return events


def get_event_types(events: list[dict[str, Any]]) -> list[str]:
    return [event["type"] for event in events]


async def test_mouse_click_releases_button(browser: zd.Browser) -> None:
    tab = await open_mouse_events_page(browser)

    await tab.mouse_click(75, 75)

    events = await get_mouse_events(tab)
    by_type = {event["type"]: event for event in events}
    assert by_type["pointerdown"]["buttons"] == 1
    assert by_type["pointerdown"]["pressure"] == 0.5
    assert by_type["pointerup"]["buttons"] == 0
    assert by_type["pointerup"]["pressure"] == 0
    assert by_type["mouseup"]["buttons"] == 0


async def test_mouse_move_does_not_release_button(browser: zd.Browser) -> None:
    tab = await open_mouse_events_page(browser)

    await tab.mouse_move(75, 75, steps=5)

    events = await get_mouse_events(tab)
    assert set(get_event_types(events)) == {"pointermove", "mousemove"}
    assert all(event["buttons"] == 0 for event in events)
    assert all(
        event["pressure"] == 0
        for event in events
        if event["type"].startswith("pointer")
    )
    assert (events[-1]["x"], events[-1]["y"]) == (75, 75)


async def test_mouse_down_move_up_holds_button(browser: zd.Browser) -> None:
    tab = await open_mouse_events_page(browser)

    await tab.mouse_down(75, 75)
    await tab.mouse_move(325, 75, steps=10)
    await tab.mouse_up(325, 75)

    events = await get_mouse_events(tab)
    assert get_event_types(events)[:2] == ["pointerdown", "mousedown"]
    assert get_event_types(events)[-2:] == ["pointerup", "mouseup"]
    held_events = events[:-2]
    assert all(event["buttons"] == 1 for event in held_events)
    assert all(
        event["pressure"] == 0.5
        for event in held_events
        if event["type"].startswith("pointer")
    )
    assert get_event_types(held_events).count("pointermove") == 10
    assert events[-2]["pressure"] == 0
    assert events[-1]["buttons"] == 0


async def test_tab_mouse_drag_relative(browser: zd.Browser) -> None:
    tab = await open_mouse_events_page(browser)

    await tab.mouse_drag((75, 75), (250, 0), relative=True, steps=5)

    events = await get_mouse_events(tab)
    assert (events[0]["x"], events[0]["y"]) == (75, 75)
    assert events[-1]["type"] == "mouseup"
    assert (events[-1]["x"], events[-1]["y"]) == (325, 75)
    assert all(event["buttons"] == 1 for event in events[:-2])


async def test_element_mouse_drag_holds_button(browser: zd.Browser) -> None:
    tab = await open_mouse_events_page(browser)
    source = await tab.select("#source")
    target = await tab.select("#target")

    await source.mouse_drag(target, steps=5)

    events = await get_mouse_events(tab)
    moves = [event for event in events if event["type"] == "pointermove"]
    assert len(moves) == 5
    assert all(event["buttons"] == 1 and event["pressure"] == 0.5 for event in moves)
    assert events[-1]["type"] == "mouseup"
    assert (events[-1]["x"], events[-1]["y"]) == (325, 75)
    assert events[-1]["buttons"] == 0
