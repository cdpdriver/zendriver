import asyncio
from typing import Any

import pytest

import zendriver as zd
from tests.sample_data import sample_file
from zendriver.cdp.fetch import RequestStage
from zendriver.cdp.network import ResourceType


async def test_set_user_agent_sets_navigator_values(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None

    await tab.set_user_agent(
        "Test user agent", accept_language="testLang", platform="TestPlatform"
    )

    navigator_user_agent = await tab.evaluate("navigator.userAgent")
    navigator_language = await tab.evaluate("navigator.language")
    navigator_platform = await tab.evaluate("navigator.platform")
    assert navigator_user_agent == "Test user agent"
    assert navigator_language == "testLang"
    assert navigator_platform == "TestPlatform"


async def test_set_user_agent_defaults_existing_user_agent(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None

    existing_user_agent = await tab.evaluate("navigator.userAgent")

    await tab.set_user_agent(accept_language="testLang")

    navigator_user_agent = await tab.evaluate("navigator.userAgent")
    navigator_language = await tab.evaluate("navigator.language")
    assert navigator_user_agent == existing_user_agent
    assert navigator_language == "testLang"


async def test_find_finds_element_by_text(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    result = await tab.find("Apples")

    assert result is not None
    assert result.tag == "li"
    assert result.text == "Apples"


async def test_find_times_out_if_element_not_found(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    with pytest.raises(asyncio.TimeoutError):
        await tab.find("Clothes", timeout=1)


async def test_select(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    result = await tab.select("li[aria-label^='Apples']")

    assert result is not None
    assert result.tag == "li"
    assert result.text == "Apples"


async def test_xpath(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    results = await tab.xpath('//li[@aria-label="Apples (42)"]')

    assert len(results) == 1
    result = results[0]

    assert result is not None
    assert result.tag == "li"
    assert result.text == "Apples"


async def test_add_handler_type_event(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    async def request_handler_1(event: zd.cdp.network.RequestWillBeSent) -> None:
        pass

    async def request_handler_2(event: zd.cdp.network.RequestWillBeSent) -> None:
        pass

    assert len(tab.handlers) == 0

    tab.add_handler(zd.cdp.network.RequestWillBeSent, request_handler_1)

    tab.add_handler(zd.cdp.network.RequestWillBeSent, request_handler_2)

    assert len(tab.handlers) == 1
    assert len(tab.handlers[zd.cdp.network.RequestWillBeSent]) == 2
    assert tab.handlers[zd.cdp.network.RequestWillBeSent] == [
        request_handler_1,
        request_handler_2,
    ]


async def test_add_handler_module_event(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    async def request_handler(event: Any) -> None:
        pass

    assert len(tab.handlers) == 0

    tab.add_handler(zd.cdp.network, request_handler)

    assert len(tab.handlers) == 27


async def test_remove_handlers(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    async def request_handler(event: zd.cdp.network.RequestWillBeSent) -> None:
        pass

    tab.add_handler(zd.cdp.network.RequestWillBeSent, request_handler)
    assert len(tab.handlers) == 1

    tab.remove_handlers()
    assert len(tab.handlers) == 0


async def test_remove_handlers_specific_event(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    async def request_handler(event: zd.cdp.network.RequestWillBeSent) -> None:
        pass

    tab.add_handler(zd.cdp.network.RequestWillBeSent, request_handler)
    assert len(tab.handlers) == 1

    tab.remove_handlers(
        zd.cdp.network.RequestWillBeSent,
    )
    assert len(tab.handlers) == 0


async def test_remove_specific_handler(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    async def request_handler_1(event: zd.cdp.network.RequestWillBeSent) -> None:
        pass

    async def request_handler_2(event: zd.cdp.network.RequestWillBeSent) -> None:
        pass

    tab.add_handler(zd.cdp.network.RequestWillBeSent, request_handler_1)
    tab.add_handler(zd.cdp.network.RequestWillBeSent, request_handler_2)
    assert len(tab.handlers) == 1
    assert len(tab.handlers[zd.cdp.network.RequestWillBeSent]) == 2

    tab.remove_handlers(zd.cdp.network.RequestWillBeSent, request_handler_1)
    assert len(tab.handlers) == 1
    assert len(tab.handlers[zd.cdp.network.RequestWillBeSent]) == 1


async def test_remove_handlers_without_event(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    async def request_handler(event: zd.cdp.network.RequestWillBeSent) -> None:
        pass

    tab.add_handler(zd.cdp.network.RequestWillBeSent, request_handler)
    assert len(tab.handlers) == 1

    with pytest.raises(ValueError) as e:
        tab.remove_handlers(handler=request_handler)
        assert str(e) == "if handler is provided, event_type should be provided as well"


async def test_wait_for_ready_state(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    await tab.wait_for_ready_state("complete")

    ready_state = await tab.evaluate("document.readyState")
    assert ready_state == "complete"


async def test_expect_request(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None

    async with tab.expect_request(sample_file("groceries.html")) as request_info:
        await tab.get(sample_file("groceries.html"))
        req = await asyncio.wait_for(request_info.value, timeout=3)
        assert type(req) is zd.cdp.network.RequestWillBeSent
        assert type(req.request) is zd.cdp.network.Request
        assert req.request.url == sample_file("groceries.html")
        assert req.request_id is not None

        response_body = await request_info.response_body
        assert response_body is not None
        assert type(response_body) is tuple


async def test_expect_response(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None

    async with tab.expect_response(sample_file("groceries.html")) as response_info:
        await tab.get(sample_file("groceries.html"))
        resp = await asyncio.wait_for(response_info.value, timeout=3)
        assert type(resp) is zd.cdp.network.ResponseReceived
        assert type(resp.response) is zd.cdp.network.Response
        assert resp.request_id is not None

        response_body = await response_info.response_body
        assert response_body is not None
        assert type(response_body) is tuple


async def test_expect_response_with_reload(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None

    async with tab.expect_response(sample_file("groceries.html")) as response_info:
        await tab.get(sample_file("groceries.html"))
        await tab.wait_for_ready_state("complete")
        await response_info.reset()
        await tab.reload()
        await tab.wait_for_ready_state("complete")
        resp = await asyncio.wait_for(response_info.value, timeout=3)
        assert type(resp) is zd.cdp.network.ResponseReceived
        assert type(resp.response) is zd.cdp.network.Response
        assert resp.request_id is not None

        response_body = await response_info.response_body
        assert response_body is not None
        assert type(response_body) is tuple


async def test_expect_download(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None

    async with tab.expect_download() as download_ex:
        await tab.get(sample_file("groceries.html"))
        await (await tab.select("#download_file")).click()
        download = await asyncio.wait_for(download_ex.value, timeout=3)
        assert type(download) is zd.cdp.browser.DownloadWillBegin
        assert download.url is not None


async def test_intercept(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None

    async with tab.intercept(
        "*/user-data.json",
        RequestStage.RESPONSE,
        ResourceType.XHR,
    ) as interception:
        await tab.get(sample_file("profile.html"))
        body, _ = await interception.response_body
        await interception.continue_request()

        assert body is not None
        # original_response = loads(body)
        # assert original_response["name"] == "Zendriver"


async def test_intercept_with_reload(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None

    async with tab.intercept(
        "*/user-data.json",
        RequestStage.RESPONSE,
        ResourceType.XHR,
    ) as interception:
        await tab.get(sample_file("profile.html"))
        await interception.continue_request()

        await interception.reset()
        body, _ = await interception.response_body
        await interception.continue_request()

        assert body is not None
        # original_response = loads(body)
        # assert original_response["name"] == "Zendriver"
