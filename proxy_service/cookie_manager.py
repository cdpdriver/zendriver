"""
Cookie Manager - 按域名管理和复用 Cookie
"""

import asyncio
from urllib.parse import urlparse
from typing import Any


class CookieManager:
    """管理不同域名的 Cookie，支持复用"""

    def __init__(self):
        self._cookies: dict[str, list[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    def get_domain(self, url: str) -> str:
        """从 URL 提取域名"""
        parsed = urlparse(url)
        return parsed.netloc or parsed.path.split("/")[0]

    async def get_cookies(self, url: str) -> list[dict[str, Any]]:
        """获取指定域名的 cookies"""
        domain = self.get_domain(url)
        async with self._lock:
            return self._cookies.get(domain, []).copy()

    async def save_cookies(self, url: str, cookies: list[dict[str, Any]]) -> None:
        """保存指定域名的 cookies"""
        domain = self.get_domain(url)
        async with self._lock:
            self._cookies[domain] = cookies

    async def clear_cookies(self, url: str | None = None) -> None:
        """清除 cookies，如果指定 url 则只清除该域名的"""
        async with self._lock:
            if url:
                domain = self.get_domain(url)
                self._cookies.pop(domain, None)
            else:
                self._cookies.clear()

    async def list_domains(self) -> list[str]:
        """列出所有已存储 cookie 的域名"""
        async with self._lock:
            return list(self._cookies.keys())
