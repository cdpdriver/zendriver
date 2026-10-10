from typing import Any

import pytest

import zendriver as zd
from zendriver.core import cloudflare as cloudflare_module


class _FakeInputElement:
    def __init__(self) -> None:
        self.attrs: dict[str, str] = {}

    async def update(self) -> "_FakeInputElement":
        return self

    def __await__(self) -> Any:
        return self.update().__await__()


class _FakeChallengeIframe:
    def __init__(self, node_id: int) -> None:
        self.node = zd.cdp.dom.Node(
            node_id=zd.cdp.dom.NodeId(node_id),
            backend_node_id=zd.cdp.dom.BackendNodeId(node_id),
            node_type=1,
            node_name="IFRAME",
            local_name="iframe",
            node_value="",
        )

    async def scroll_into_view(self) -> None:
        pass


class _HostElementNeverQueried:
    async def query_selector(self, selector: str) -> None:
        raise AssertionError(
            "verify_cf() queried the shadow host for the response input; "
            "it should query the document (tab.query_selector) instead"
        )


async def test_verify_cf_clicks_checkbox_when_input_is_document_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge_iframe = _FakeChallengeIframe(node_id=42)

    async def fake_wait_for_challenge(
        _tab: zd.Tab, _timeout: float
    ) -> tuple[Any, Any, Any]:
        return _HostElementNeverQueried(), object(), challenge_iframe

    monkeypatch.setattr(
        cloudflare_module,
        "cf_wait_for_interactive_challenge",
        fake_wait_for_challenge,
    )

    box_model = zd.cdp.dom.BoxModel(
        content=zd.cdp.dom.Quad([0.0, 0.0, 100.0, 0.0, 100.0, 50.0, 0.0, 50.0]),
        padding=zd.cdp.dom.Quad([]),
        border=zd.cdp.dom.Quad([]),
        margin=zd.cdp.dom.Quad([]),
        width=100,
        height=50,
    )

    async def fake_send(cdp_obj: Any, _is_update: bool = False) -> Any:
        next(cdp_obj)
        return box_model

    tab = zd.Tab.__new__(zd.Tab)
    monkeypatch.setattr(tab, "send", fake_send)

    input_element = _FakeInputElement()
    query_selector_calls: list[str] = []

    async def fake_query_selector(selector: str) -> _FakeInputElement | None:
        query_selector_calls.append(selector)
        return input_element

    monkeypatch.setattr(tab, "query_selector", fake_query_selector)

    click_calls: list[tuple[float, float]] = []

    async def fake_mouse_click(x: float, y: float) -> None:
        click_calls.append((x, y))
        input_element.attrs["value"] = "solved"

    monkeypatch.setattr(tab, "mouse_click", fake_mouse_click)

    await cloudflare_module.verify_cf(tab, click_delay=0, timeout=5)

    assert click_calls, "verify_cf() never clicked the checkbox"
    assert query_selector_calls[0] == "input[name=cf-turnstile-response]"
