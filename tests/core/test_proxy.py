import asyncio
import base64
import http.server
import threading
import urllib.parse
from typing import AsyncIterator, Iterator

import pytest

import zendriver as zd
from zendriver.core.proxy import ProxyForwarder, UpstreamProxy, pipe

USERNAME = "user"
PASSWORD = "p@ss:word"
QUOTED_CREDENTIALS = f"{USERNAME}:{urllib.parse.quote(PASSWORD, safe='')}"
PAGE_TEXT = "hello through the proxy"


class HttpProxy:
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.sockets[0].getsockname()[1])

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            request_line, *header_lines = head.decode().split("\r\n")[:-2]
            headers = dict(line.split(": ", 1) for line in header_lines)
            authorization = headers.pop("Proxy-Authorization", None)
            expected = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
            if authorization != f"Basic {expected}":
                writer.write(
                    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                    b"Proxy-Authenticate: Basic\r\nContent-Length: 0\r\n\r\n"
                )
                return
            method, target, version = request_line.split(" ")
            self.requests.append(f"{method} {target}")
            if method == "CONNECT":
                host, port = target.rsplit(":", 1)
                upstream_reader, upstream_writer = await asyncio.open_connection(
                    host, int(port)
                )
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            else:
                url = urllib.parse.urlsplit(target)
                upstream_reader, upstream_writer = await asyncio.open_connection(
                    url.hostname, url.port
                )
                lines = [f"{method} {url.path} {version}"]
                lines += [f"{name}: {value}" for name, value in headers.items()]
                upstream_writer.write("\r\n".join([*lines, "", ""]).encode())
            await pipe(reader, writer, upstream_reader, upstream_writer)
        finally:
            writer.close()


class Socks5Proxy:
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.sockets[0].getsockname()[1])

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            _, method_count = await reader.readexactly(2)
            if 0x02 not in await reader.readexactly(method_count):
                writer.write(b"\x05\xff")
                return
            writer.write(b"\x05\x02")
            _, username_length = await reader.readexactly(2)
            username = (await reader.readexactly(username_length)).decode()
            (password_length,) = await reader.readexactly(1)
            password = (await reader.readexactly(password_length)).decode()
            if (username, password) != (USERNAME, PASSWORD):
                writer.write(b"\x01\x01")
                return
            writer.write(b"\x01\x00")

            _, _, _, address_type = await reader.readexactly(4)
            assert address_type == 0x01
            host = ".".join(str(b) for b in await reader.readexactly(4))
            port = int.from_bytes(await reader.readexactly(2), "big")
            self.requests.append(f"{host}:{port}")
            upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
            writer.write(b"\x05\x00\x00\x01" + bytes(4) + bytes(2))
            await pipe(reader, writer, upstream_reader, upstream_writer)
        finally:
            writer.close()


async def start_proxy(proxy: HttpProxy | Socks5Proxy) -> None:
    proxy.server = await asyncio.start_server(proxy.handle, "127.0.0.1", 0)


@pytest.fixture
async def http_proxy() -> AsyncIterator[HttpProxy]:
    proxy = HttpProxy()
    await start_proxy(proxy)
    yield proxy
    assert proxy.server is not None
    proxy.server.close()


@pytest.fixture
async def socks5_proxy() -> AsyncIterator[Socks5Proxy]:
    proxy = Socks5Proxy()
    await start_proxy(proxy)
    yield proxy
    assert proxy.server is not None
    proxy.server.close()


@pytest.fixture
def page_url() -> Iterator[str]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            data = f"<html><body><p id='text'>{PAGE_TEXT}</p></body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


async def get_through_forwarder(forwarder: ProxyForwarder, request: bytes) -> bytes:
    port = int(forwarder.proxy_server.rsplit(":", 1)[1])
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(request)
    try:
        return await asyncio.wait_for(reader.read(), 10)
    finally:
        writer.close()


@pytest.mark.parametrize("scheme", ["http", "socks5"])
async def test_create_context_with_authenticated_proxy(
    browser: zd.Browser,
    http_proxy: HttpProxy,
    socks5_proxy: Socks5Proxy,
    page_url: str,
    scheme: str,
) -> None:
    proxy = http_proxy if scheme == "http" else socks5_proxy
    tab = await browser.create_context(
        proxy_server=f"{scheme}://{QUOTED_CREDENTIALS}@127.0.0.1:{proxy.port}",
        proxy_bypass_list=["<-loopback>"],
    )
    try:
        await tab.get(page_url)
        text = await tab.select("#text")
        assert text.text == PAGE_TEXT
        assert proxy.requests
    finally:
        await tab.close()


async def test_create_context_without_credentials_does_not_forward(
    browser: zd.Browser, page_url: str
) -> None:
    forwarder_count = len(browser._proxy_forwarders)
    tab = await browser.create_context(proxy_server="http://127.0.0.1:1")
    try:
        await tab.get(page_url)
        text = await tab.select("#text")
        assert text.text == PAGE_TEXT
        assert len(browser._proxy_forwarders) == forwarder_count
    finally:
        await tab.close()


@pytest.mark.parametrize("scheme", ["http", "socks5"])
async def test_forwarder_connect(
    http_proxy: HttpProxy, socks5_proxy: Socks5Proxy, page_url: str, scheme: str
) -> None:
    proxy = http_proxy if scheme == "http" else socks5_proxy
    upstream = UpstreamProxy.from_url(
        f"{scheme}://{QUOTED_CREDENTIALS}@127.0.0.1:{proxy.port}"
    )
    assert upstream is not None
    forwarder = ProxyForwarder(upstream)
    await forwarder.start()
    try:
        authority = urllib.parse.urlsplit(page_url).netloc
        response = await get_through_forwarder(
            forwarder,
            f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n"
            f"GET / HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\n\r\n".encode(),
        )
        assert response.startswith(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        assert PAGE_TEXT.encode() in response
    finally:
        await forwarder.close()


@pytest.mark.parametrize("scheme", ["http", "socks5"])
async def test_forwarder_rejected_credentials(
    http_proxy: HttpProxy, socks5_proxy: Socks5Proxy, page_url: str, scheme: str
) -> None:
    proxy = http_proxy if scheme == "http" else socks5_proxy
    upstream = UpstreamProxy.from_url(f"{scheme}://user:wrong@127.0.0.1:{proxy.port}")
    assert upstream is not None
    forwarder = ProxyForwarder(upstream)
    await forwarder.start()
    try:
        authority = urllib.parse.urlsplit(page_url).netloc
        response = await get_through_forwarder(
            forwarder, f"CONNECT {authority} HTTP/1.1\r\n\r\n".encode()
        )
        assert response.startswith(b"HTTP/1.1 502 ")
        assert not proxy.requests
    finally:
        await forwarder.close()


def test_upstream_proxy_from_url() -> None:
    assert UpstreamProxy.from_url("http://127.0.0.1:8080") is None
    assert UpstreamProxy.from_url("socks5://[::1]:1080") is None

    upstream = UpstreamProxy.from_url(f"https://{QUOTED_CREDENTIALS}@example.com")
    assert upstream == UpstreamProxy("https", "example.com", 443, USERNAME, PASSWORD)

    with pytest.raises(ValueError):
        UpstreamProxy.from_url("socks4://user:pass@127.0.0.1:1080")
