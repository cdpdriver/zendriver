"""
Zendriver Proxy Service

一个简单的浏览器代理服务，支持：
- 多并发
- Cookie 管理（按域名复用）
- 等待指定元素出现
- 超时控制
"""

from .browser_pool import BrowserPool
from .cookie_manager import CookieManager
from .fetcher import Fetcher, FetchResult

__all__ = [
    "BrowserPool",
    "CookieManager",
    "Fetcher",
    "FetchResult",
]
