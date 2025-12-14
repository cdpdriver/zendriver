"""
Cookie Manager - 按 (域名, 代理) 管理和复用 Cookie
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .proxy_config import ProxyConfig


class CookieManager:
    """管理不同 (域名, 代理) 组合的 Cookie，支持复用"""

    def __init__(self):
        # key = (domain, proxy_server | None)
        self._cookies: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    def get_domain(self, url: str) -> str:
        """从 URL 提取域名"""
        # 如果没有 scheme，添加一个以便正确解析
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        parsed = urlparse(url)
        return parsed.netloc or parsed.path.split("/")[0]

    def _make_key(
        self, url: str, proxy: ProxyConfig | None
    ) -> tuple[str, str | None]:
        """生成存储 key"""
        domain = self.get_domain(url)
        proxy_key = proxy.proxy_key if proxy else None
        return (domain, proxy_key)

    async def get_cookies(
        self, url: str, proxy: ProxyConfig | None = None
    ) -> list[dict[str, Any]]:
        """获取指定 (域名, 代理) 的 cookies"""
        key = self._make_key(url, proxy)
        async with self._lock:
            return self._cookies.get(key, []).copy()

    async def save_cookies(
        self,
        url: str,
        cookies: list[dict[str, Any]],
        proxy: ProxyConfig | None = None,
    ) -> None:
        """保存指定 (域名, 代理) 的 cookies"""
        key = self._make_key(url, proxy)
        async with self._lock:
            self._cookies[key] = cookies

    async def clear_cookies(
        self,
        url: str | None = None,
        proxy: ProxyConfig | None = None,
    ) -> None:
        """
        清除 cookies

        - url=None, proxy=None: 清除所有
        - url 指定: 清除该域名的（如果 proxy 也指定则精确匹配）
        - proxy 指定: 清除该代理的所有域名
        """
        async with self._lock:
            if url is None and proxy is None:
                # 清除所有
                self._cookies.clear()
            elif url is not None and proxy is not None:
                # 精确匹配 (domain, proxy)
                key = self._make_key(url, proxy)
                self._cookies.pop(key, None)
            elif url is not None:
                # 清除指定域名的所有代理
                domain = self.get_domain(url)
                keys_to_remove = [k for k in self._cookies if k[0] == domain]
                for k in keys_to_remove:
                    self._cookies.pop(k, None)
            else:
                # 清除指定代理的所有域名
                proxy_key = proxy.proxy_key if proxy else None
                keys_to_remove = [k for k in self._cookies if k[1] == proxy_key]
                for k in keys_to_remove:
                    self._cookies.pop(k, None)

    async def list_keys(self) -> list[dict[str, Any]]:
        """列出所有已存储 cookie 的 (domain, proxy) 组合"""
        async with self._lock:
            return [
                {"domain": domain, "proxy": proxy}
                for (domain, proxy) in self._cookies.keys()
            ]

    async def list_domains(self) -> list[str]:
        """列出所有已存储 cookie 的域名（兼容旧接口）"""
        async with self._lock:
            # 返回唯一的域名列表
            domains = set(domain for (domain, _) in self._cookies.keys())
            return list(domains)
