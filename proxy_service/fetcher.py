"""
Fetcher - 核心抓取逻辑
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zendriver import cdp

from .browser_pool import BrowserPool
from .cookie_manager import CookieManager
from .page_loader import CloudflareConfig, PageLoader

if TYPE_CHECKING:
    from .proxy_config import ProxyConfig

logger = logging.getLogger(__name__)

# 额外超时时间（秒）- 在 page_loader timeout 基础上增加的缓冲
EXTRA_TIMEOUT_BUFFER = 30.0


@dataclass
class FetchResult:
    """抓取结果"""

    success: bool
    html: str
    url: str
    elapsed: float
    error: str | None = None

    # Cloudflare 状态
    cf_detected: bool = False
    cf_solved: bool = False
    cf_retries: int = 0

    # 页面状态
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": self.success,
            "html": self.html,
            "url": self.url,
            "elapsed": round(self.elapsed, 3),
        }
        if self.error:
            result["error"] = self.error
        if self.status != "ok":
            result["status"] = self.status

        # Cloudflare 信息
        result["cloudflare"] = {
            "detected": self.cf_detected,
            "solved": self.cf_solved,
            "retries": self.cf_retries,
        }
        return result


class Fetcher:
    """核心抓取器"""

    def __init__(
        self,
        browser_pool: BrowserPool,
        cookie_manager: CookieManager,
        default_timeout: float = 30.0,
    ):
        self.browser_pool = browser_pool
        self.cookie_manager = cookie_manager
        self.default_timeout = default_timeout
        self.page_loader = PageLoader()

    async def fetch(
        self,
        url: str,
        wait_for: str | None = None,
        timeout: float | None = None,
        proxy: ProxyConfig | None = None,
        cf_config: CloudflareConfig | None = None,
    ) -> FetchResult:
        """
        抓取页面 HTML

        Args:
            url: 目标 URL
            wait_for: 等待的 CSS 选择器（可选）
            timeout: 超时时间（秒）
            proxy: 代理配置（可选）
            cf_config: Cloudflare 配置（可选）

        Returns:
            FetchResult
        """
        timeout = timeout or self.default_timeout
        # 总超时 = 页面超时 + 额外缓冲（用于 acquire/release 等操作）
        total_timeout = timeout + EXTRA_TIMEOUT_BUFFER
        start_time = time.time()

        try:
            # 使用总超时包裹整个操作，防止任何操作无限挂起
            return await asyncio.wait_for(
                self._do_fetch(url, wait_for, timeout, proxy, cf_config, start_time),
                timeout=total_timeout,
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error(f"Total timeout ({total_timeout}s) exceeded for {url}")
            return FetchResult(
                success=False,
                html="",
                url=url,
                elapsed=elapsed,
                error=f"Total timeout ({total_timeout}s) exceeded",
            )
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(f"Unexpected error fetching {url}")
            return FetchResult(
                success=False,
                html="",
                url=url,
                elapsed=elapsed,
                error=str(e),
            )

    async def _do_fetch(
        self,
        url: str,
        wait_for: str | None,
        timeout: float,
        proxy: ProxyConfig | None,
        cf_config: CloudflareConfig | None,
        start_time: float,
    ) -> FetchResult:
        """实际执行抓取操作"""
        tab = None

        try:
            # 1. 获取 Tab（会等待信号量，并设置代理认证）
            tab = await self.browser_pool.acquire(proxy)

            # 2. 加载该 (域名, 代理) 的 Cookies
            await self._load_cookies(tab, url, proxy)

            # 3. 使用 PageLoader 加载页面（处理 CF 验证）
            load_result = await self.page_loader.load(
                tab=tab,
                url=url,
                wait_for=wait_for,
                timeout=timeout,
                cf_config=cf_config,
            )

            # 4. 保存 Cookies（按域名+代理）
            if load_result.success:
                await self._save_cookies(tab, url, proxy)

            elapsed = time.time() - start_time
            return FetchResult(
                success=load_result.success,
                html=load_result.html,
                url=load_result.final_url,
                elapsed=elapsed,
                error=load_result.error,
                cf_detected=load_result.cf_detected,
                cf_solved=load_result.cf_solved,
                cf_retries=load_result.cf_retries,
                status=load_result.status,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(f"Error fetching {url}")
            return FetchResult(
                success=False,
                html="",
                url=url,
                elapsed=elapsed,
                error=str(e),
            )

        finally:
            # 5. 释放 Tab
            if tab:
                await self.browser_pool.release(tab)

    async def _load_cookies(
        self, tab, url: str, proxy: ProxyConfig | None
    ) -> None:
        """加载 (域名, 代理) 对应的 cookies 到 tab"""
        try:
            cookies_data = await self.cookie_manager.get_cookies(url, proxy)
            if not cookies_data:
                return

            # 转换为 CookieParam 对象
            cookie_params = []
            for c in cookies_data:
                param = cdp.network.CookieParam(
                    name=c["name"],
                    value=c["value"],
                    domain=c.get("domain"),
                    path=c.get("path"),
                    secure=c.get("secure"),
                    http_only=c.get("http_only"),
                    expires=cdp.network.TimeSinceEpoch(c["expires"])
                    if c.get("expires")
                    else None,
                )
                cookie_params.append(param)

            if cookie_params:
                await tab.send(cdp.storage.set_cookies(cookie_params))
                logger.debug(
                    f"Loaded {len(cookie_params)} cookies for {url} "
                    f"(proxy: {proxy.proxy_key if proxy else None})"
                )

        except Exception as e:
            logger.warning(f"Failed to load cookies: {e}")

    async def _save_cookies(
        self, tab, url: str, proxy: ProxyConfig | None
    ) -> None:
        """从 tab 保存 cookies 到管理器（按域名+代理）"""
        try:
            cookies = await tab.send(cdp.storage.get_cookies())
            if not cookies:
                return

            # 转换为可序列化的字典
            cookies_data = []
            for c in cookies:
                cookies_data.append(
                    {
                        "name": c.name,
                        "value": c.value,
                        "domain": c.domain,
                        "path": c.path,
                        "secure": c.secure,
                        "http_only": c.http_only,
                        "expires": c.expires,
                    }
                )

            await self.cookie_manager.save_cookies(url, cookies_data, proxy)
            logger.debug(
                f"Saved {len(cookies_data)} cookies for {url} "
                f"(proxy: {proxy.proxy_key if proxy else None})"
            )

        except Exception as e:
            logger.warning(f"Failed to save cookies: {e}")
