import zendriver as zd

from tests.sample_data import sample_file
from zendriver import SpecialKeys, KeyModifiers, KeyEvents


async def test_visible_events(browser: zd.Browser) -> None:
    """Test keyboard events with contenteditable div."""
    # Open the page
    main_page = await browser.get(sample_file("simple_editor.html"))

    text_part = await main_page.find('//*[@id="editor"]')

    await text_part.mouse_click("left")
    for _ in range(50):
        if await main_page.evaluate("document.activeElement.id") == "editor":
            break
        await main_page.sleep(0.1)
    await text_part.send_keys("Hello, world!")

    payloads = KeyEvents.from_mixed_input(
        [
            " This is another sentence",
            SpecialKeys.ENTER,
            ("a", KeyModifiers.Ctrl),
            ("c", KeyModifiers.Ctrl),
            SpecialKeys.ARROW_UP,
            ("v", KeyModifiers.Ctrl),
            " This is pasted text. 👍",
        ]
    )

    await text_part.send_keys(payloads)
    check_part = await main_page.find('//*[@id="editor"]')
    assert len(check_part.children) == 4, "Expected 4 children after operations"

    expected_output = [
        "Hello, world! This is another sentence",
        "<div>&nbsp;This is pasted text. 👍</div>",
        "Hello, world! This is another sentence",
        "<div><br></div>",
    ]

    for expected, actual_text in zip(expected_output, check_part.children):
        actual_html = await actual_text.get_html()
        assert actual_html == expected, f"Expected '{expected}', got '{actual_html}'"


async def test_escape_key_popup(browser: zd.Browser) -> None:
    """Test escape key functionality to close a popup."""
    main_page = await browser.get(sample_file("special_key_detector.html"))
    # the page registers its listeners in a script at the end of the body
    await main_page.wait_for_ready_state("complete")

    status_check = await main_page.find('//*[@id="status"]')
    assert (
        status_check.text == "Ready - Click button to open popUp"
    ), "There is something wrong with the page"

    button = await main_page.find('//*[@id="mainpageButton"]')
    await button.mouse_click("left")

    await status_check
    assert (
        status_check.text == "popUp is OPEN - Press Escape to close"
    ), "Popup did not open correctly"

    pop_up = await main_page.find('//*[@id="mainpage"]/div')
    await pop_up.send_keys(SpecialKeys.ESCAPE)

    await status_check
    assert (
        status_check.text == "popUp is CLOSED - Click button to open again"
    ), "Popup did not close correctly"
