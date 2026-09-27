import asyncio

import pytest

import zendriver as zd
from tests.sample_data import sample_file

REQUEST_WIDEVINE_ACCESS = """
navigator.requestMediaKeySystemAccess("com.widevine.alpha", [{
    initDataTypes: ["cenc"],
    videoCapabilities: [{ contentType: 'video/mp4; codecs="avc1.42E01E"' }],
}]).then(() => true, () => false)
"""


async def wait_for_widevine(page: zd.Tab) -> None:
    while not await page.evaluate(REQUEST_WIDEVINE_ACCESS, await_promise=True):
        await page.sleep(1)


async def test_widevine_is_supported(browser: zd.Browser) -> None:
    if "chromium" in str(browser.config.browser_executable_path).lower():
        pytest.skip("Chromium does not include Widevine")

    page = await browser.get(sample_file("groceries.html"))

    # outside of Linux, Chrome's component updater installs Widevine after startup
    await asyncio.wait_for(wait_for_widevine(page), timeout=120)
