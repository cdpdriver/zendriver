import zendriver as zd
from tests.conftest import CreateBrowser


async def test_multiple_browsers_diff_userdata(
    create_browser: type[CreateBrowser],
) -> None:
    config = create_browser().config

    browser1 = await zd.start(config)
    browser2 = await zd.start(config)
    browser3 = await zd.start(config)

    assert not browser1.config.uses_custom_data_dir
    assert not browser2.config.uses_custom_data_dir
    assert not browser3.config.uses_custom_data_dir

    # make sure ports are unique
    ports = {browser1.config.port, browser2.config.port, browser3.config.port}
    assert len(ports) == 3

    # make sure user data dirs are unique
    udds = {
        browser1.config.user_data_dir,
        browser2.config.user_data_dir,
        browser3.config.user_data_dir,
    }
    assert len(udds) == 3

    # Awaiting the page alone leaves this flaky on a loaded runner: the cached target still holds
    # the pre-navigation title, which is the URL, so wait for the load and then refresh it.
    page1 = await browser1.get("https://example.com/one")
    await page1.wait_for_ready_state("complete")
    await page1.update_target()
    assert page1.target
    assert page1.target.title == "Example Domain"

    page2 = await browser2.get("https://example.com/two")
    await page2.wait_for_ready_state("complete")
    await page2.update_target()
    assert page2.target
    assert page2.target.title == "Example Domain"

    page3 = await browser3.get("https://example.com/three")
    await page3.wait_for_ready_state("complete")
    await page3.update_target()
    assert page3.target
    assert page3.target.title == "Example Domain"

    await browser1.stop()
    await browser2.stop()
    await browser3.stop()
