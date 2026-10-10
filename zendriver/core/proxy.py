from __future__ import annotations

import asyncio
import base64
import ipaddress
import logging
import ssl
import urllib.parse
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_PORTS = {"http": 80, "https": 443, "socks5": 1080, "socks5h": 1080}
HOP_BY_HOP_HEADERS = {
    "proxy-authorization",
    "proxy-connection",
    "connection",
    "keep-alive",
}
TIMEOUT = 30
BUFFER_SIZE = 65536


class ProxyError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass
class UpstreamProxy:
    scheme: str
    host: str
    port: int
    username: str
    password: str
    ssl_context: ssl.SSLContext | None = None

    @classmethod
    def from_url(
        cls, url: str, ssl_context: ssl.SSLContext | None = None
    ) -> UpstreamProxy | None:
        """
        parse a proxy url such as ``http://user:pass@host:port``.
        returns None if the url contains no credentials, since chrome can use such a proxy directly.
        """
        parsed = urllib.parse.urlsplit(url)
        if parsed.username is None and parsed.password is None:
            return None
        scheme = parsed.scheme.lower()
        if scheme not in DEFAULT_PORTS:
            raise ValueError(
                f"unsupported scheme for authenticated proxy: {parsed.scheme!r}, "
                f"expected one of {', '.join(DEFAULT_PORTS)}"
            )
        if not parsed.hostname:
            raise ValueError(f"proxy url has no host: {url!r}")
        username = urllib.parse.unquote(parsed.username or "")
        password = urllib.parse.unquote(parsed.password or "")
        if scheme.startswith("socks") and (
            len(username.encode()) > 255 or len(password.encode()) > 255
        ):
            raise ValueError("SOCKS5 username and password must be at most 255 bytes")
        return cls(
            scheme=scheme,
            host=parsed.hostname,
            port=parsed.port or DEFAULT_PORTS[scheme],
            username=username,
            password=password,
            ssl_context=ssl_context,
        )

    @property
    def is_socks(self) -> bool:
        return self.scheme.startswith("socks")

    @property
    def authorization(self) -> str:
        credentials = f"{self.username}:{self.password}".encode()
        return "Basic " + base64.b64encode(credentials).decode("ascii")

    async def open_connection(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        tls: ssl.SSLContext | None = None
        if self.scheme == "https":
            tls = self.ssl_context or ssl.create_default_context()
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, ssl=tls), TIMEOUT
            )
        except (OSError, asyncio.TimeoutError) as e:
            raise ProxyError(
                f"could not connect to proxy {self.host}:{self.port}: {e!r}"
            ) from e

    async def open_tunnel(
        self, host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await self.open_connection()
        try:
            if self.is_socks:
                await asyncio.wait_for(
                    self._socks5_connect(reader, writer, host, port), TIMEOUT
                )
            else:
                await asyncio.wait_for(
                    self._http_connect(reader, writer, host, port), TIMEOUT
                )
        except BaseException as e:
            writer.close()
            if isinstance(e, (OSError, asyncio.IncompleteReadError)):
                raise ProxyError(f"proxy closed the connection: {e!r}") from e
            if isinstance(e, asyncio.TimeoutError):
                raise ProxyError("timed out waiting for the proxy") from e
            raise
        return reader, writer

    async def _http_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        host: str,
        port: int,
    ) -> None:
        authority = format_authority(host, port)
        writer.write(
            (
                f"CONNECT {authority} HTTP/1.1\r\n"
                f"Host: {authority}\r\n"
                f"Proxy-Authorization: {self.authorization}\r\n"
                "\r\n"
            ).encode()
        )
        response = await reader.readuntil(b"\r\n\r\n")
        status_line = response.split(b"\r\n", 1)[0].decode("latin-1")
        if status_line.split(" ", 2)[1:2] != ["200"]:
            raise ProxyError(f"proxy refused CONNECT {authority}: {status_line}")

    async def _socks5_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        host: str,
        port: int,
    ) -> None:
        writer.write(b"\x05\x02\x00\x02")
        version, method = await reader.readexactly(2)
        if version != 5:
            raise ProxyError("proxy is not a SOCKS5 proxy")
        if method == 0x02:
            username = self.username.encode()
            password = self.password.encode()
            writer.write(
                bytes([1, len(username)]) + username + bytes([len(password)]) + password
            )
            _, auth_status = await reader.readexactly(2)
            if auth_status != 0:
                raise ProxyError("SOCKS5 proxy rejected the username or password")
        elif method != 0x00:
            raise ProxyError("SOCKS5 proxy does not support username/password auth")

        writer.write(
            b"\x05\x01\x00" + encode_socks5_address(host) + port.to_bytes(2, "big")
        )
        _, reply, _, address_type = await reader.readexactly(4)
        if reply != 0:
            raise ProxyError(
                f"SOCKS5 proxy could not connect to {format_authority(host, port)} "
                f"(reply code {reply})"
            )
        if address_type == 0x01:
            await reader.readexactly(4 + 2)
        elif address_type == 0x04:
            await reader.readexactly(16 + 2)
        else:
            (length,) = await reader.readexactly(1)
            await reader.readexactly(length + 2)


class ProxyForwarder:
    """
    local unauthenticated http proxy which forwards all traffic to an authenticated upstream proxy.
    chrome can not pass proxy credentials by itself, so it is pointed to this forwarder instead.
    """

    def __init__(self, upstream: UpstreamProxy):
        self.upstream = upstream
        self._server: asyncio.Server | None = None
        self._client_tasks: set[asyncio.Task[None]] = set()

    @property
    def proxy_server(self) -> str:
        if self._server is None:
            raise RuntimeError("proxy forwarder is not started")
        host, port = self._server.sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, "127.0.0.1", 0, limit=BUFFER_SIZE
        )
        logger.debug(
            "forwarding proxy %s to %s://%s:%d",
            self.proxy_server,
            self.upstream.scheme,
            self.upstream.host,
            self.upstream.port,
        )

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        for task in self._client_tasks:
            task.cancel()
        await asyncio.gather(*self._client_tasks, return_exceptions=True)
        await self._server.wait_closed()
        self._server = None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._client_tasks.add(task)
        try:
            await self._forward(reader, writer)
        except ProxyError as e:
            logger.warning("proxy request failed: %s", e)
            writer.write(
                f"HTTP/1.1 {e.status} Proxy Error\r\n"
                "Content-Length: 0\r\nConnection: close\r\n\r\n".encode()
            )
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            logger.debug("proxy client connection closed", exc_info=True)
        finally:
            self._client_tasks.discard(task)
            writer.close()

    async def _forward(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), TIMEOUT)
        except asyncio.TimeoutError:
            return
        request_line, *header_lines = head.decode("latin-1").split("\r\n")[:-2]
        try:
            method, target, version = request_line.split(" ")
        except ValueError:
            raise ProxyError(f"malformed request line: {request_line!r}", 400)

        if method == "CONNECT":
            host, port = split_authority(target)
            upstream_reader, upstream_writer = await self.upstream.open_tunnel(
                host, port
            )
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await pipe(reader, writer, upstream_reader, upstream_writer)
            return

        url = urllib.parse.urlsplit(target)
        if url.scheme != "http" or not url.hostname:
            raise ProxyError(f"unsupported request target: {target!r}", 400)
        headers = [
            line
            for line in header_lines
            if line.split(":", 1)[0].strip().lower() not in HOP_BY_HOP_HEADERS
        ]
        headers.append("Connection: close")
        if self.upstream.is_socks:
            upstream_reader, upstream_writer = await self.upstream.open_tunnel(
                url.hostname, url.port or 80
            )
            path = urllib.parse.urlunsplit(("", "", url.path or "/", url.query, ""))
            request_line = f"{method} {path} {version}"
        else:
            upstream_reader, upstream_writer = await self.upstream.open_connection()
            headers.append(f"Proxy-Authorization: {self.upstream.authorization}")
        upstream_writer.write(
            "\r\n".join([request_line, *headers, "", ""]).encode("latin-1")
        )
        await pipe(reader, writer, upstream_reader, upstream_writer)


async def pipe(
    reader_a: asyncio.StreamReader,
    writer_a: asyncio.StreamWriter,
    reader_b: asyncio.StreamReader,
    writer_b: asyncio.StreamWriter,
) -> None:
    tasks = [
        asyncio.create_task(copy_stream(reader_a, writer_b)),
        asyncio.create_task(copy_stream(reader_b, writer_a)),
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        writer_b.close()


async def copy_stream(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    while data := await reader.read(BUFFER_SIZE):
        writer.write(data)
        await writer.drain()
    if writer.can_write_eof():
        writer.write_eof()


def split_authority(authority: str) -> tuple[str, int]:
    url = urllib.parse.urlsplit(f"//{authority}")
    try:
        port = url.port
    except ValueError:
        port = None
    if not url.hostname or port is None:
        raise ProxyError(f"invalid CONNECT target: {authority!r}", 400)
    return url.hostname, port


def format_authority(host: str, port: int) -> str:
    if ":" in host:
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def encode_socks5_address(host: str) -> bytes:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        domain = host.encode("idna")
        return bytes([0x03, len(domain)]) + domain
    if address.version == 4:
        return b"\x01" + address.packed
    return b"\x04" + address.packed
