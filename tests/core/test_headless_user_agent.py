import http.server
import json
import threading
from typing import Iterator

import pytest

import zendriver as zd

EchoServer = tuple[str, list[dict[str, str]]]


@pytest.fixture
def echo_server() -> Iterator[EchoServer]:
    """Serve a page on 127.0.0.1 and record the headers of every request, with
    lower-cased names."""
    requests: list[dict[str, str]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(
                {name.lower(): value for name, value in self.headers.items()}
            )
            body = b"<html><body><p>hello</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/", requests
    finally:
        server.shutdown()
        server.server_close()


async def test_user_agent_is_a_visible_chrome_with_client_hints(
    browser: zd.Browser, echo_server: EchoServer
) -> None:
    """A headless browser must not tell from a visible one: no "HeadlessChrome" token,
    and the client hints a visible Chrome exposes and sends."""
    url, requests = echo_server
    tab = await browser.get(url)

    user_agent = await tab.evaluate("navigator.userAgent")
    assert "Headless" not in user_agent
    assert "Chrome/" in user_agent

    hints = json.loads(
        await tab.evaluate(
            "navigator.userAgentData"
            ".getHighEntropyValues(['platformVersion', 'fullVersionList'])"
            ".then(JSON.stringify)",
            await_promise=True,
        )
    )
    assert hints["brands"]
    assert hints["platformVersion"]
    assert hints["fullVersionList"]

    page_request = next(r for r in requests if r.get("sec-fetch-dest") == "document")
    assert "Headless" not in page_request["user-agent"]
    assert page_request.get("sec-ch-ua")
    assert page_request.get("sec-ch-ua-platform")
