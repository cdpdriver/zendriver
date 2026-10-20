import http.server
import json
import re
import sys
import threading
from typing import Iterator

import pytest

import zendriver as zd
from zendriver.core import browser as browser_module

EchoServer = tuple[str, list[dict[str, str]]]

USER_AGENTS = {
    "Windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) HeadlessChrome/155.0.0.0 Safari/537.36",
    "macOS": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) HeadlessChrome/155.0.0.0 Safari/537.36",
    "Linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) HeadlessChrome/155.0.0.0 Safari/537.36",
    "Chrome OS": "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "Android": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36",
}


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


@pytest.mark.parametrize(
    ("platform_name", "user_agent"), list(USER_AGENTS.items()), ids=list(USER_AGENTS)
)
def test_user_agent_platform(platform_name: str, user_agent: str) -> None:
    assert browser_module._user_agent_platform(user_agent) == platform_name


def test_headless_user_agent_of_this_host() -> None:
    """The metadata built for a browser running on this host only carries the
    required hints, in the form Chrome reports them: Chrome fills in the others."""
    host = browser_module._host_platform()
    assert host in USER_AGENTS
    result = browser_module._headless_user_agent(USER_AGENTS[host])
    assert result is not None
    user_agent, metadata = result

    assert user_agent == USER_AGENTS[host].replace("Headless", "")
    assert metadata.platform == host
    assert metadata.architecture in ("x86", "arm")
    if sys.platform.startswith("linux"):
        assert metadata.platform_version == ""
    else:
        assert re.fullmatch(r"\d+\.\d+\.\d+", metadata.platform_version)
    assert metadata.model == ""
    assert metadata.mobile is False
    assert metadata.brands is None
    assert metadata.full_version_list is None
    assert metadata.bitness is None


def test_headless_user_agent_of_another_platform() -> None:
    """A browser running on another platform gets no metadata from this host."""
    host = browser_module._host_platform()
    other = next(ua for name, ua in USER_AGENTS.items() if name != host)
    assert browser_module._headless_user_agent(other) is None


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
            "navigator.userAgentData.getHighEntropyValues("
            "['architecture', 'bitness', 'platformVersion', 'fullVersionList']"
            ").then(JSON.stringify)",
            await_promise=True,
        )
    )
    assert hints["brands"]
    assert hints["fullVersionList"]
    assert hints["bitness"]
    assert hints["architecture"] in ("x86", "arm")

    if browser.config.headless:
        # the override carries the user agent and metadata built at startup
        assert browser.headless_user_agent is not None
        override_user_agent, metadata = browser.headless_user_agent
        assert user_agent == override_user_agent
        assert hints["platform"] == metadata.platform
        assert hints["platformVersion"] == metadata.platform_version
        assert hints["architecture"] == metadata.architecture
    else:
        assert browser.headless_user_agent is None

    page_request = next(r for r in requests if r.get("sec-fetch-dest") == "document")
    assert "Headless" not in page_request["user-agent"]
    assert page_request.get("sec-ch-ua")
    assert page_request.get("sec-ch-ua-platform")
