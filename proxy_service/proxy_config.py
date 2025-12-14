"""
Proxy Config - 代理配置解析
"""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ProxyConfig:
    """代理配置"""

    server: str  # http://host:port（用于浏览器启动参数）
    proxy_key: str  # http://user@host:port（用于缓存 key，区分不同用户名）
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    scheme: str = "http"

    @classmethod
    def parse(cls, proxy_url: str) -> "ProxyConfig":
        """
        解析代理 URL

        支持格式:
        - http://host:port
        - http://user:pass@host:port
        - socks5://host:port
        """
        parsed = urlparse(proxy_url)

        if not parsed.hostname or not parsed.port:
            raise ValueError(f"Invalid proxy URL: {proxy_url}")

        scheme = parsed.scheme or "http"
        server = f"{scheme}://{parsed.hostname}:{parsed.port}"

        # proxy_key 包含用户名，用于区分同一 ip:port 但不同用户的代理
        if parsed.username:
            proxy_key = f"{scheme}://{parsed.username}@{parsed.hostname}:{parsed.port}"
        else:
            proxy_key = server

        return cls(
            server=server,
            proxy_key=proxy_key,
            host=parsed.hostname,
            port=parsed.port,
            username=parsed.username,
            password=parsed.password,
            scheme=scheme,
        )

    @property
    def needs_auth(self) -> bool:
        """是否需要认证"""
        return bool(self.username and self.password)

    def to_browser_arg(self) -> str:
        """转换为浏览器启动参数"""
        return f"--proxy-server={self.server}"

    def __hash__(self) -> int:
        return hash(self.proxy_key)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ProxyConfig):
            return self.proxy_key == other.proxy_key
        return False
