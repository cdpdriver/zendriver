import asyncio

import pytest

import zendriver as zd

pytestmark = pytest.mark.external


async def get_test_result(label: zd.Element) -> zd.Element | None:
    assert label.parent is not None
    container = await label.parent.update()
    last_child = container.children[-1]
    # a placeholder svg is shown in place of the result until the checks finish
    return last_child if last_child.tag == "strong" else None


async def wait_for_test_result(page: zd.Tab, label: zd.Element) -> zd.Element:
    while (result := await get_test_result(label)) is None:
        await page.sleep(0.5)
    return result


async def test_browserscan(browser: zd.Browser) -> None:
    page = await browser.get("https://www.browserscan.net/bot-detection")

    label = await page.find("Test Results:", timeout=15)
    result = await asyncio.wait_for(wait_for_test_result(page, label), timeout=15)

    assert result.text == "Normal"
