"""
Proxy Config - 代理配置解析
"""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ProxyConfig:
    """代理配置"""

    server: str  # http://host:port（用于浏览器参数和缓存 key）
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

        return cls(
            server=server,
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
        return hash(self.server)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ProxyConfig):
            return self.server == other.server
        return False
