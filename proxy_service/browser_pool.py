"""
Browser Pool - 浏览器实例池，支持并发控制
"""

import asyncio
import logging
from typing import TYPE_CHECKING

import zendriver as zd

if TYPE_CHECKING:
    from zendriver import Browser, Tab

logger = logging.getLogger(__name__)


class BrowserPool:
    """浏览器池，管理浏览器实例和并发"""

    def __init__(
        self,
        max_concurrent: int = 5,
        headless: bool = True,
        browser_args: list[str] | None = None,
    ):
        self.max_concurrent = max_concurrent
        self.headless = headless
        self.browser_args = browser_args or []

        self._browser: "Browser | None" = None
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        """启动浏览器"""
        async with self._lock:
            if self._started:
                return

            logger.info("Starting browser...")
            self._browser = await zd.start(
                headless=self.headless,
                browser_args=self._browser_args_with_defaults(),
            )
            self._started = True
            logger.info("Browser started")

    def _browser_args_with_defaults(self) -> list[str]:
        """合并默认参数"""
        defaults = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
        ]
        return defaults + self.browser_args

    async def stop(self) -> None:
        """关闭浏览器"""
        async with self._lock:
            if self._browser and self._started:
                logger.info("Stopping browser...")
                await self._browser.stop()
                self._browser = None
                self._started = False
                logger.info("Browser stopped")

    async def acquire(self) -> "Tab":
        """
        获取一个新的 Tab（会等待信号量）
        返回的 Tab 需要调用 release() 释放
        """
        await self._semaphore.acquire()

        if not self._started:
            await self.start()

        try:
            # 创建新 Tab
            tab = await self._browser.get("about:blank", new_tab=True)
            return tab
        except Exception:
            self._semaphore.release()
            raise

    async def release(self, tab: "Tab") -> None:
        """释放 Tab"""
        try:
            await tab.close()
        except Exception as e:
            logger.warning(f"Error closing tab: {e}")
        finally:
            self._semaphore.release()

    @property
    def browser(self) -> "Browser | None":
        return self._browser

    @property
    def is_started(self) -> bool:
        return self._started
