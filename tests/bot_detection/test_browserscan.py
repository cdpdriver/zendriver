import pytest

import zendriver as zd

pytestmark = pytest.mark.external


async def test_browserscan(browser: zd.Browser) -> None:
    page = await browser.get("https://www.browserscan.net/bot-detection")

    # wait for the page to fully load
    await page.wait_for_ready_state("complete")

    # give the javascript some time to finish executing
    await page.wait(2)

    element = await page.find_element_by_text("Test Results:")
    assert (
        element is not None
        and element.parent is not None
        and isinstance(element.parent.children[-1], zd.Element)
    )
    assert element.parent.children[-1].text == "Normal"
