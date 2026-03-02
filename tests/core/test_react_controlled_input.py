"""
Tests that reproduce the React controlled input silent failure bug.

React installs an instance-level value property setter on controlled inputs
(its _valueTracker mechanism). Direct `el.value = x` assignments go through
this setter, updating the tracker's "last known value". When an 'input' event
then fires, React checks `el.value === tracker.getValue()` — they match —
so React concludes nothing changed and does NOT call onChange.

zendriver's clear_input() and clear_input_by_deleting() previously used direct
.value assignments, making them silently ineffective against React controlled
inputs. The real-world consequence is a "mixed value" when filling a pre-filled
input (e.g. old value "10", new value "25" → result "025" or "1025").
"""

import asyncio

import zendriver as zd

from tests.sample_data import sample_file


async def test_clear_input_does_not_notify_react(browser: zd.Browser) -> None:
    """
    clear_input() previously used element.value = "" which goes through React's
    tracker setter, updating both the DOM and trackerValue to "". No input event
    was dispatched, so React's onChange check never ran. React state stayed at "10".
    """
    tab = await browser.get(sample_file("react-controlled-input-test.html"))

    input_el = await tab.select("#controlled-input")

    assert (
        await tab.evaluate("document.getElementById('state-value').textContent") == "10"
    )
    assert (
        await tab.evaluate("document.getElementById('change-count').textContent") == "0"
    )

    await input_el.clear_input()
    await asyncio.sleep(0.1)

    # Expected: React state is "" (the clear was communicated to React)
    # Actual before fix: React state is still "10" (React was never notified)
    assert (
        await tab.evaluate("document.getElementById('state-value').textContent") == ""
    )


async def test_clear_input_by_deleting_does_not_notify_react(
    browser: zd.Browser,
) -> None:
    """
    clear_input_by_deleting() previously used n.value = n.value.slice(1) on each
    iteration. Each direct .value assignment went through React's tracker setter,
    updating both the DOM and trackerValue simultaneously. When the input event
    fired, React checked el.value === trackerValue — they matched — so onChange
    was never called. React state stayed at "10".
    """
    tab = await browser.get(sample_file("react-controlled-input-test.html"))

    input_el = await tab.select("#controlled-input")

    assert (
        await tab.evaluate("document.getElementById('state-value').textContent") == "10"
    )
    assert (
        await tab.evaluate("document.getElementById('change-count').textContent") == "0"
    )

    await input_el.clear_input_by_deleting()
    await asyncio.sleep(0.1)

    # Expected: React state is "" (every deletion was communicated to React)
    # Actual before fix: React state was "10" or a partial value (silent failure)
    assert (
        await tab.evaluate("document.getElementById('state-value').textContent") == ""
    )


async def test_fill_react_controlled_input_produces_mixed_value(
    browser: zd.Browser,
) -> None:
    """
    The real-world consequence: after clear_input_by_deleting silently fails to
    notify React, React's async scheduler re-renders and restores the DOM to its
    controlled value ("10"). Typing "25" then inserts into "10" instead of an
    empty field, producing a mixed value like "025" or "1025" instead of "25".
    """
    tab = await browser.get(sample_file("react-controlled-input-test.html"))

    input_el = await tab.select("#controlled-input")

    # Step 1: Try to clear — before fix: silently fails at React level
    await input_el.clear_input_by_deleting()

    # Step 2: Simulate React's async re-render committing the old controlled state.
    # In a real app this happens automatically between automation operations.
    # React uses the native prototype setter to revert the DOM to its controlled value.
    await tab.evaluate("window.simulateReactRerender()")
    await asyncio.sleep(0.05)

    # Step 3: Type the new value — before fix: DOM held old value, producing mixed result
    await input_el.send_keys("25")
    await asyncio.sleep(0.1)

    value = await input_el.apply("(el) => el.value")

    # Expected: "25"   (clear worked, inserting into empty field gives "25")
    # Actual before fix: mixed value like "025" or "1025"
    assert value == "25"
