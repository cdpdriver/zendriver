import asyncio
import pathlib
from collections.abc import Generator
from typing import Any

import pytest

import zendriver as zd
from tests.sample_data import sample_file
from zendriver.cdp.fetch import RequestStage
from zendriver.cdp.network import ResourceType
from zendriver.core.connection import ProtocolException


def make_node(
    node_id: int,
    node_name: str,
    *,
    children: list[zd.cdp.dom.Node] | None = None,
    content_document: zd.cdp.dom.Node | None = None,
    attributes: list[str] | None = None,
    parent_id: int | None = None,
) -> zd.cdp.dom.Node:
    return zd.cdp.dom.Node(
        node_id=zd.cdp.dom.NodeId(node_id),
        backend_node_id=zd.cdp.dom.BackendNodeId(node_id),
        node_type=9 if node_name == "#document" else 1,
        node_name=node_name,
        local_name="" if node_name == "#document" else node_name.lower(),
        node_value="",
        parent_id=zd.cdp.dom.NodeId(parent_id) if parent_id is not None else None,
        child_node_count=len(children) if children is not None else None,
        children=children,
        attributes=attributes,
        content_document=content_document,
    )


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
        await tab.find("Clothes", timeout=0.2)


async def test_select(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    result = await tab.select("li[aria-label^='Apples']")

    assert result is not None
    assert result.tag == "li"
    assert result.text == "Apples"


async def test_query_selector_all_include_frames_queries_nested_iframe_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    top_match = make_node(
        3,
        "SPAN",
        attributes=["class", "match", "data-location", "top"],
        parent_id=2,
    )
    inner_match = make_node(
        9,
        "SPAN",
        attributes=["class", "match", "data-location", "inner"],
        parent_id=8,
    )
    inner_doc = make_node(
        8,
        "#document",
        children=[inner_match],
    )
    inner_iframe = make_node(
        7,
        "IFRAME",
        content_document=inner_doc,
        parent_id=5,
    )
    outer_match = make_node(
        6,
        "SPAN",
        attributes=["class", "match", "data-location", "outer"],
        parent_id=5,
    )
    outer_doc = make_node(
        5,
        "#document",
        children=[outer_match, inner_iframe],
    )
    outer_iframe = make_node(
        4,
        "IFRAME",
        content_document=outer_doc,
        parent_id=2,
    )
    cross_origin_iframe = make_node(
        10,
        "IFRAME",
        content_document=None,
        parent_id=2,
    )
    body = make_node(
        2,
        "BODY",
        children=[top_match, outer_iframe, cross_origin_iframe],
        parent_id=1,
    )
    doc = make_node(1, "#document", children=[body])

    matches_by_document_id = {
        doc.node_id: [top_match.node_id],
        outer_doc.node_id: [outer_match.node_id],
        inner_doc.node_id: [inner_match.node_id],
    }
    queried_document_ids: list[zd.cdp.dom.NodeId] = []

    async def send(
        cdp_obj: Generator[dict[str, Any], dict[str, Any], Any],
        _is_update: bool = False,
    ) -> Any:
        command = next(cdp_obj)
        if command["method"] == "DOM.getDocument":
            return doc
        if command["method"] == "DOM.querySelectorAll":
            node_id = zd.cdp.dom.NodeId(command["params"]["nodeId"])
            queried_document_ids.append(node_id)
            return matches_by_document_id[node_id]
        raise AssertionError(f"Unexpected CDP command: {command['method']}")

    tab = zd.Tab.__new__(zd.Tab)
    monkeypatch.setattr(tab, "send", send)

    results = await tab.query_selector_all(".match", _include_frames=True)

    assert {result.attrs["data-location"] for result in results} == {
        "top",
        "outer",
        "inner",
    }
    assert set(queried_document_ids) == {
        doc.node_id,
        outer_doc.node_id,
        inner_doc.node_id,
    }


async def test_xpath(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    results = await tab.xpath('//li[@aria-label="Apples (42)"]')

    assert len(results) == 1
    result = results[0]

    assert result is not None
    assert result.tag == "li"
    assert result.text == "Apples"


async def test_xpath_no_results(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    results = await tab.xpath('//li[@aria-label="Nonexistent Item"]', timeout=0.5)

    assert len(results) == 0


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

    assert set(tab.handlers) == set(zd.cdp.util.get_event_classes(zd.cdp.network))
    assert zd.cdp.network.RequestWillBeSent in tab.handlers
    assert zd.cdp.network.ResourceType not in tab.handlers


async def test_add_handler_module_event_receives_events(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    received: list[Any] = []

    async def page_handler(event: Any) -> None:
        received.append(event)

    tab.add_handler(zd.cdp.page, page_handler)
    await tab.reload()
    await tab.wait(1)

    assert any(isinstance(event, zd.cdp.page.LoadEventFired) for event in received)


async def test_sync_handlers_are_each_called(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    first_called = asyncio.Event()
    second_called = asyncio.Event()
    loop = asyncio.get_running_loop()

    def first_handler(event: zd.cdp.page.LoadEventFired) -> None:
        loop.call_soon_threadsafe(first_called.set)

    def second_handler(event: zd.cdp.page.LoadEventFired) -> None:
        loop.call_soon_threadsafe(second_called.set)

    tab.add_handler(zd.cdp.page.LoadEventFired, first_handler)
    tab.add_handler(zd.cdp.page.LoadEventFired, second_handler)
    await tab.reload()

    await asyncio.wait_for(asyncio.gather(first_called.wait(), second_called.wait()), 5)


async def test_remove_handlers(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    async def request_handler(event: zd.cdp.network.RequestWillBeSent) -> None:
        pass

    tab.add_handler(zd.cdp.network.RequestWillBeSent, request_handler)
    assert len(tab.handlers) == 1

    tab.remove_handlers()
    assert len(tab.handlers) == 0


async def test_handler_raising_type_error_is_called_once(
    browser: zd.Browser,
) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    calls: list[tuple[Any, ...]] = []
    called = asyncio.Event()

    async def handler(*args: Any) -> None:
        calls.append(args)
        called.set()
        raise TypeError("raised by the handler itself")

    tab.add_handler(zd.cdp.page.LoadEventFired, handler)
    await tab.reload()
    await asyncio.wait_for(called.wait(), 5)
    await tab.wait(0.5)

    assert len(calls) == 1
    assert calls[0][1] is tab


async def test_handler_without_connection_argument_receives_event(
    browser: zd.Browser,
) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    received: list[Any] = []
    called = asyncio.Event()

    async def handler(event: zd.cdp.page.LoadEventFired) -> None:
        received.append(event)
        called.set()

    tab.add_handler(zd.cdp.page.LoadEventFired, handler)
    await tab.reload()
    await asyncio.wait_for(called.wait(), 5)

    assert isinstance(received[0], zd.cdp.page.LoadEventFired)


async def test_remove_handlers_for_event_without_handlers(
    browser: zd.Browser,
) -> None:
    tab = await browser.get(sample_file("groceries.html"))

    tab.remove_handlers(zd.cdp.network.RequestWillBeSent)

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


async def test_wait_for_ready_state_times_out_when_evaluate_hangs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def evaluate(*args: Any, **kwargs: Any) -> None:
        # simulate a CDP response that never arrives
        await asyncio.Event().wait()

    tab = zd.Tab.__new__(zd.Tab)
    monkeypatch.setattr(tab, "evaluate", evaluate)

    # the outer wait_for is only a safety net so the test can't hang; its
    # TimeoutError has no message, so `match` tells the two apart
    with pytest.raises(asyncio.TimeoutError, match="until complete"):
        await asyncio.wait_for(tab.wait_for_ready_state("complete", timeout=1), 5)


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


@pytest.mark.external
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


@pytest.mark.external
async def test_intercept_with_reload(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None

    async with tab.intercept(
        "*/user-data.json",
        RequestStage.RESPONSE,
        ResourceType.XHR,
    ) as interception:
        await tab.get(sample_file("profile.html"))
        await interception.response_body
        await interception.continue_request()

        await interception.reset()
        await tab.reload()
        body, _ = await interception.response_body
        await interception.continue_request()

        assert body is not None
        # original_response = loads(body)
        # assert original_response["name"] == "Zendriver"


@pytest.mark.external
async def test_handler_wont_reenable_without_params(browser: zd.Browser) -> None:
    # Test the custom enabled domains are not reenabled without params after handler is added
    tab = browser.main_tab
    assert tab is not None

    tab.add_handler(zd.cdp.fetch.RequestPaused, lambda _: None)
    # enable fetch with custom pattern
    await tab.send(
        zd.cdp.fetch.enable(
            [
                zd.cdp.fetch.RequestPattern(
                    url_pattern="*/user-data.json",
                    request_stage=RequestStage.RESPONSE,
                    resource_type=ResourceType.XHR,
                )
            ]
        )
    )
    assert zd.cdp.fetch in tab.manually_enabled_domains

    async with tab.expect_response(sample_file("profile.html")) as response_info:
        # This will hang if _register_handlers reenables fetch without params
        await tab.get(sample_file("profile.html"))
        assert zd.cdp.fetch not in tab.enabled_domains
        response_body = await response_info.response_body
        assert response_body is not None


async def test_manual_disable_send(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None
    tab.add_handler(zd.cdp.network, lambda _: None)
    # disable send will overwrite auto enabled domain from handler
    await tab.send(zd.cdp.network.disable())
    assert zd.cdp.network not in tab.manually_enabled_domains
    assert zd.cdp.network not in tab.enabled_domains


@pytest.mark.external
async def test_auto_enable_domain(browser: zd.Browser) -> None:
    tab = browser.main_tab
    assert tab is not None
    tab.add_handler(zd.cdp.network, lambda _: None)
    # disable send will overwrite auto enabled domain from handler
    await tab.get(sample_file("profile.html"))
    assert zd.cdp.network not in tab.manually_enabled_domains
    assert zd.cdp.network in tab.enabled_domains


async def test_evaluate_complex_object_no_error(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("complex_object.html"))
    await tab.wait_for_ready_state("complete")

    result = await tab.evaluate(
        "document.querySelector('body:not(.no-js)')", return_by_value=False
    )
    assert result is not None

    # This is similar to the original failing case but more likely to trigger the error
    body_with_complex_refs = await tab.evaluate("document.body", return_by_value=False)
    assert body_with_complex_refs is not None


async def test_evaluate_return_by_value_complex_object(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("complex_object.html"))
    await tab.wait_for_ready_state("complete")

    expression = "document.querySelector('body:not(.no-js)')"

    # Fetching a complex object with return_by_value=True is unsupported because there is no
    # way to represent the object as a simple data structure.
    with pytest.raises(ProtocolException):
        _ = await tab.evaluate(expression, return_by_value=True)

    result_by_value_false = await tab.evaluate(expression, return_by_value=False)
    assert (
        result_by_value_false is not None
    )  # Should return the deep serialized value, not a tuple


async def test_evaluate_return_by_value_simple_json(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("simple_json.html"))
    await tab.wait_for_ready_state("complete")

    expression = "JSON.parse(document.querySelector('#obj').textContent)"

    result_by_value_true = await tab.evaluate(expression, return_by_value=True)
    assert result_by_value_true == {"a": "x", "b": 3.14159}

    result_by_value_false = await tab.evaluate(expression, return_by_value=False)
    assert result_by_value_false == [
        ["a", {"type": "string", "value": "x"}],
        ["b", {"type": "number", "value": 3.14159}],
    ]


async def test_evaluate_return_by_value_falsy(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("simple_json.html"))
    await tab.wait_for_ready_state("complete")

    expr_template = "JSON.parse(document.querySelector('%s').textContent)"

    assert await tab.evaluate(expr_template % "#zero") == 0
    assert await tab.evaluate(expr_template % "#empty_array") == []
    assert await tab.evaluate(expr_template % "#null") is None


async def test_evaluate_stress_test_complex_objects(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("complex_object.html"))
    await tab.wait_for_ready_state("complete")

    # Test various DOM queries that could trigger reference chain issues
    # Each test case is a tuple of (expression, return_by_value, expected_type_or_validator)
    test_cases = [
        ("document.querySelector('body:not(.no-js)')", False, lambda x: x is not None),
        ("document.documentElement", False, lambda x: x is not None),
        ("document.querySelector('*')", False, lambda x: x is not None),
        ("document.body.parentElement", False, lambda x: x is not None),
        ("document.getElementById('content')", False, lambda x: x is not None),
        (
            "document.body.complexStructure ? 'has complex structure' : 'no structure'",
            True,
            str,
        ),
        ("document.readyState", True, str),
        ("navigator.userAgent", True, str),
        ("window.location.href", True, str),
        ("document.title", True, str),
    ]

    for expression, return_by_value, validator in test_cases:
        result = await tab.evaluate(expression, return_by_value=return_by_value)
        # Verify the result is usable and matches expected type/validation
        if callable(validator):
            assert validator(
                result
            ), f"Result validation failed for '{expression}': {result}"
        elif isinstance(validator, type):
            assert isinstance(
                result, validator
            ), f"Expected {validator} for '{expression}', got {type(result)}: {result}"
        else:
            raise ValueError("Validator must be a type or callable")


async def test_awaiting_new_tab_does_not_raise(browser: zd.Browser) -> None:
    """Awaiting a tab nothing was sent to yet used to raise ValueError (#186)."""
    tab = await browser.get(sample_file("groceries.html"), new_tab=True)

    await tab

    assert await tab.evaluate("1 + 1") == 2


async def test_response_to_cancelled_command_does_not_stop_listener(
    browser: zd.Browser,
) -> None:
    """A response arriving after its command was cancelled used to crash the listener (#89)."""
    tab = await browser.get(sample_file("groceries.html"))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            tab.evaluate(
                "new Promise((r) => setTimeout(() => r(1), 500))", await_promise=True
            ),
            0.1,
        )
    # resolves after the cancelled command's response has been received
    assert (
        await asyncio.wait_for(
            tab.evaluate(
                "new Promise((r) => setTimeout(() => r(2), 1000))", await_promise=True
            ),
            5,
        )
        == 2
    )

    assert tab.listener is not None and tab.listener.running
    assert await tab.evaluate("1 + 1") == 2


async def test_events_are_not_retained(browser: zd.Browser) -> None:
    """Every received event used to be kept in memory for the connection's lifetime (#198)."""
    tab = await browser.get(sample_file("groceries.html"))
    tab.add_handler(zd.cdp.page.LoadEventFired, lambda _: None)
    await tab.reload()
    await tab.evaluate("1 + 1")

    assert tab.mapper == {}


async def test_set_download_path_creates_directory(
    browser: zd.Browser, tmp_path: pathlib.Path
) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    download_path = tmp_path / "nested" / "downloads"

    await tab.set_download_path(download_path)

    assert download_path.is_dir()


async def test_is_scrolled_to_bottom(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    await tab.evaluate("document.body.style.height = '5000px'")

    assert not await tab.is_scrolled_to_bottom()

    await tab.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")

    assert await tab.is_scrolled_to_bottom()


async def test_shadow_children_includes_closed_shadow_root(
    browser: zd.Browser,
) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    await tab.evaluate(
        """
        const root = document.querySelector("h1").attachShadow({ mode: "closed" });
        root.innerHTML = "<button id='shadow-button'>Shadow</button>";
        """
    )

    heading = await tab.select("h1")

    assert [child.tag for child in heading.shadow_children] == ["button"]
    assert heading.shadow_children[0].attrs["id"] == "shadow-button"


async def test_get_position_abs_includes_scroll_offset(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    await tab.evaluate("document.body.style.height = '5000px'")
    button = await tab.select("#download_file")

    await tab.evaluate("window.scrollTo(0, 100)")
    position = await button.get_position(abs=True)

    assert position is not None
    assert position.abs_y == position.top + 100 + position.height / 2


async def test_element_get_only_returns_html_attributes(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    button = await tab.select("#download_file")

    assert button.get("id") == "download_file"
    assert button.get("missing") is None
    assert button.get("items") is None


async def test_element_get_returns_empty_attribute_value(browser: zd.Browser) -> None:
    tab = await browser.get(sample_file("groceries.html"))
    await tab.evaluate("document.querySelector('#download_file').disabled = true")
    button = await tab.select("#download_file")

    assert button.get("disabled") == ""
