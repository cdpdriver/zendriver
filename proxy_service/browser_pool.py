"""
Browser Pool - 多代理浏览器实例池，支持并发控制
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import zendriver as zd
from zendriver import cdp

if TYPE_CHECKING:
    from zendriver import Browser, Tab

    from .proxy_config import ProxyConfig

logger = logging.getLogger(__name__)


class BrowserPool:
    """多代理浏览器池，管理多个浏览器实例和并发"""

    def __init__(
        self,
        max_concurrent: int = 5,
        headless: bool = True,
        browser_args: list[str] | None = None,
        browser_executable_path: str | None = None,
    ):
        self.max_concurrent = max_concurrent
        self.headless = headless
        self.browser_args = browser_args or []
        self.browser_executable_path = browser_executable_path

        # proxy_server -> Browser 实例
        self._browsers: dict[str | None, Browser] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._started = False

    def _browser_args_with_defaults(
        self, proxy: ProxyConfig | None = None
    ) -> list[str]:
        """合并默认参数和代理参数"""
        defaults = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
        ]
        args = defaults + self.browser_args

        # 添加代理参数
        if proxy:
            args.append(proxy.to_browser_arg())

        return args

    async def _get_or_create_browser(
        self, proxy: ProxyConfig | None = None
    ) -> "Browser":
        """获取或创建指定代理的浏览器实例"""
        key = proxy.server if proxy else None

        async with self._lock:
            if key not in self._browsers:
                logger.info(f"Creating browser for proxy: {key}")
                start_kwargs = {
                    "headless": self.headless,
                    "browser_args": self._browser_args_with_defaults(proxy),
                }
                if self.browser_executable_path:
                    start_kwargs["browser_executable_path"] = self.browser_executable_path
                browser = await zd.start(**start_kwargs)
                self._browsers[key] = browser
                self._started = True
                logger.info(f"Browser created for proxy: {key}")

            return self._browsers[key]

    async def start(self) -> None:
        """预启动默认浏览器（无代理）"""
        await self._get_or_create_browser(None)

    async def stop(self) -> None:
        """关闭所有浏览器实例"""
        async with self._lock:
            for key, browser in self._browsers.items():
                try:
                    logger.info(f"Stopping browser for proxy: {key}")
                    await browser.stop()
                except Exception as e:
                    logger.warning(f"Error stopping browser {key}: {e}")

            self._browsers.clear()
            self._started = False
            logger.info("All browsers stopped")

    async def acquire(self, proxy: ProxyConfig | None = None) -> "Tab":
        """
        获取一个新的 Tab（会等待信号量）

        Args:
            proxy: 代理配置，None 表示不使用代理

        Returns:
            配置好的 Tab 实例
        """
        await self._semaphore.acquire()

        try:
            browser = await self._get_or_create_browser(proxy)

            # 创建新 Tab
            tab = await browser.get("about:blank", new_tab=True)

            # 如果代理需要认证，设置处理器
            if proxy and proxy.needs_auth:
                await self._setup_proxy_auth(tab, proxy)

            return tab
        except Exception:
            self._semaphore.release()
            raise

    async def _setup_proxy_auth(self, tab: "Tab", proxy: "ProxyConfig") -> None:
        """设置代理认证处理器"""

        async def handle_auth_required(event: cdp.fetch.AuthRequired) -> None:
            """处理代理认证挑战 (HTTP 407)"""
            logger.debug(f"Proxy auth required for: {event.request.url}")
            auth_response = cdp.fetch.AuthChallengeResponse(
                response="ProvideCredentials",
                username=proxy.username,
                password=proxy.password,
            )
            await tab.send(
                cdp.fetch.continue_with_auth(event.request_id, auth_response)
            )

        async def handle_request_paused(event: cdp.fetch.RequestPaused) -> None:
            """继续被暂停的请求"""
            try:
                await tab.send(cdp.fetch.continue_request(request_id=event.request_id))
            except Exception as e:
                logger.warning(f"Error continuing request: {e}")

        # 注册事件处理器
        tab.add_handler(cdp.fetch.AuthRequired, handle_auth_required)
        tab.add_handler(cdp.fetch.RequestPaused, handle_request_paused)

        # 启用 Fetch 域，处理认证请求
        await tab.send(cdp.fetch.enable(handle_auth_requests=True))
        logger.debug(f"Proxy auth setup complete for {proxy.server}")

    async def release(self, tab: "Tab") -> None:
        """释放 Tab"""
        try:
            await tab.close()
        except Exception as e:
            logger.warning(f"Error closing tab: {e}")
        finally:
            self._semaphore.release()

    @property
    def is_started(self) -> bool:
        return self._started

    async def get_stats(self) -> list[dict]:
        """获取浏览器实例统计信息"""
        async with self._lock:
            stats = []
            for key, browser in self._browsers.items():
                tab_count = len([t for t in browser.tabs if not t.closed])
                stats.append({"proxy": key, "tabs": tab_count})
            return stats
