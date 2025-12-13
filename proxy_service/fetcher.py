"""
Fetcher - 核心抓取逻辑
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from zendriver import cdp

from .browser_pool import BrowserPool
from .cookie_manager import CookieManager

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """抓取结果"""

    success: bool
    html: str
    url: str
    elapsed: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.success,
            "html": self.html,
            "url": self.url,
            "elapsed": round(self.elapsed, 3),
        }
        if self.error:
            result["error"] = self.error
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

    async def fetch(
        self,
        url: str,
        wait_for: str | None = None,
        timeout: float | None = None,
    ) -> FetchResult:
        """
        抓取页面 HTML

        Args:
            url: 目标 URL
            wait_for: 等待的 CSS 选择器（可选）
            timeout: 超时时间（秒）

        Returns:
            FetchResult
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()
        tab = None
        html = ""
        final_url = url
        error = None

        try:
            # 1. 获取 Tab（会等待信号量）
            tab = await self.browser_pool.acquire()

            # 2. 加载该域名的 Cookies
            await self._load_cookies(tab, url)

            # 3. 导航到 URL
            await tab.get(url)

            # 4. 等待页面加载
            if wait_for:
                # 等待指定元素出现
                try:
                    await asyncio.wait_for(
                        self._wait_for_selector(tab, wait_for),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    error = f"Timeout waiting for selector: {wait_for}"
                    logger.warning(error)
            else:
                # 等待页面加载完成
                try:
                    await asyncio.wait_for(
                        tab.wait_for_ready_state(),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    error = "Timeout waiting for page load"
                    logger.warning(error)

            # 5. 获取最终 URL 和 HTML
            final_url = tab.url or url
            html = await tab.get_content()

            # 6. 保存 Cookies
            await self._save_cookies(tab, url)

            elapsed = time.time() - start_time
            return FetchResult(
                success=error is None,
                html=html,
                url=final_url,
                elapsed=elapsed,
                error=error,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(f"Error fetching {url}")
            return FetchResult(
                success=False,
                html=html,
                url=final_url,
                elapsed=elapsed,
                error=str(e),
            )

        finally:
            # 7. 释放 Tab
            if tab:
                await self.browser_pool.release(tab)

    async def _wait_for_selector(self, tab, selector: str) -> None:
        """等待元素出现"""
        while True:
            try:
                elem = await tab.select(selector)
                if elem:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.1)

    async def _load_cookies(self, tab, url: str) -> None:
        """加载域名对应的 cookies 到 tab"""
        try:
            cookies_data = await self.cookie_manager.get_cookies(url)
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
                logger.debug(f"Loaded {len(cookie_params)} cookies for {url}")

        except Exception as e:
            logger.warning(f"Failed to load cookies: {e}")

    async def _save_cookies(self, tab, url: str) -> None:
        """从 tab 保存 cookies 到管理器"""
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

            await self.cookie_manager.save_cookies(url, cookies_data)
            logger.debug(f"Saved {len(cookies_data)} cookies for {url}")

        except Exception as e:
            logger.warning(f"Failed to save cookies: {e}")
