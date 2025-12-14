"""
Browser Pool - 多代理浏览器实例池，支持并发控制和自动恢复
"""

from __future__ import annotations

import asyncio
import logging
import time
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
        browser_max_age: int = 3600,  # 浏览器最大存活时间（秒）
        health_check_interval: int = 60,  # 健康检查间隔（秒）
    ):
        self.max_concurrent = max_concurrent
        self.headless = headless
        self.browser_args = browser_args or []
        self.browser_executable_path = browser_executable_path
        self.browser_max_age = browser_max_age
        self.health_check_interval = health_check_interval

        # proxy_server -> Browser 实例
        self._browsers: dict[str | None, Browser] = {}
        self._browser_start_times: dict[str | None, float] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._started = False
        self._health_check_task: asyncio.Task | None = None

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
        key = proxy.proxy_key if proxy else None

        async with self._lock:
            if key not in self._browsers:
                logger.info(f"Creating browser for proxy: {key}")
                start_kwargs = {
                    "headless": self.headless,
                    "browser_args": self._browser_args_with_defaults(proxy),
                    "sandbox": False,
                }
                if self.browser_executable_path:
                    start_kwargs["browser_executable_path"] = self.browser_executable_path
                browser = await zd.start(**start_kwargs)
                self._browsers[key] = browser
                self._browser_start_times[key] = time.time()
                self._started = True
                logger.info(f"Browser created for proxy: {key}")

            return self._browsers[key]

    async def start(self) -> None:
        """预启动默认浏览器（无代理）并启动健康检查"""
        await self._get_or_create_browser(None)
        # 启动健康检查任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Browser pool started with health check")

    async def stop(self) -> None:
        """关闭所有浏览器实例"""
        # 停止健康检查任务
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        async with self._lock:
            for key, browser in self._browsers.items():
                try:
                    logger.info(f"Stopping browser for proxy: {key}")
                    await asyncio.wait_for(browser.stop(), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Browser stop timeout for {key}")
                except Exception as e:
                    logger.warning(f"Error stopping browser {key}: {e}")

            self._browsers.clear()
            self._browser_start_times.clear()
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
            # 创建浏览器（带超时）
            browser = await asyncio.wait_for(
                self._get_or_create_browser(proxy),
                timeout=30.0
            )

            # 创建新 Tab（带超时）
            tab = await asyncio.wait_for(
                browser.get("about:blank", new_tab=True),
                timeout=10.0
            )

            # 如果代理需要认证，设置处理器（带超时）
            if proxy and proxy.needs_auth:
                await asyncio.wait_for(
                    self._setup_proxy_auth(tab, proxy),
                    timeout=10.0
                )

            return tab

        except asyncio.TimeoutError as e:
            logger.error(f"Acquire timeout: {e}")
            self._semaphore.release()
            raise
        except Exception as e:
            logger.error(f"Acquire error: {e}")
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
        logger.debug(f"Proxy auth setup complete for {proxy.proxy_key}")

    async def release(self, tab: "Tab") -> None:
        """释放 Tab（确保信号量一定释放）"""
        try:
            # Tab 关闭设置超时，避免卡住
            await asyncio.wait_for(tab.close(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Tab close timeout, forcing release")
        except Exception as e:
            logger.warning(f"Error closing tab: {e}")
        finally:
            # 无论如何都释放信号量
            self._semaphore.release()

    async def _health_check_loop(self) -> None:
        """定期健康检查"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._check_and_restart_browsers()
            except asyncio.CancelledError:
                logger.info("Health check loop cancelled")
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def _check_and_restart_browsers(self) -> None:
        """检查并重启有问题的浏览器"""
        now = time.time()
        browsers_to_restart: list[str | None] = []

        async with self._lock:
            for key in list(self._browsers.keys()):
                browser = self._browsers[key]
                start_time = self._browser_start_times.get(key, now)
                age = now - start_time

                # 检查是否超龄
                if age > self.browser_max_age:
                    logger.info(f"Browser {key} exceeded max age ({age:.0f}s), scheduling restart")
                    browsers_to_restart.append(key)
                    continue

                # 检查是否响应
                if not await self._is_browser_healthy(browser):
                    logger.warning(f"Browser {key} is unhealthy, scheduling restart")
                    browsers_to_restart.append(key)

        # 在锁外重启浏览器
        for key in browsers_to_restart:
            await self._restart_browser(key)

    async def _is_browser_healthy(self, browser: "Browser") -> bool:
        """检查浏览器是否健康"""
        try:
            main_tab = browser.main_tab
            if main_tab is None:
                return False
            # 尝试执行简单操作
            await asyncio.wait_for(
                main_tab.evaluate("1+1"),
                timeout=5.0
            )
            return True
        except Exception as e:
            logger.debug(f"Browser health check failed: {e}")
            return False

    async def _restart_browser(self, key: str | None) -> None:
        """重启指定浏览器"""
        async with self._lock:
            if key in self._browsers:
                old_browser = self._browsers.pop(key)
                self._browser_start_times.pop(key, None)
                logger.info(f"Restarting browser for proxy: {key}")

                # 异步关闭旧浏览器
                asyncio.create_task(self._safe_close_browser(old_browser, key))

    async def _safe_close_browser(self, browser: "Browser", key: str | None) -> None:
        """安全关闭浏览器"""
        try:
            await asyncio.wait_for(browser.stop(), timeout=10.0)
            logger.info(f"Old browser closed for proxy: {key}")
        except Exception as e:
            logger.warning(f"Error closing old browser {key}: {e}")

    @property
    def is_started(self) -> bool:
        return self._started

    def get_semaphore_status(self) -> dict:
        """获取信号量状态"""
        return {
            "total": self.max_concurrent,
            "available": self._semaphore._value,
            "in_use": self.max_concurrent - self._semaphore._value,
        }

    async def get_stats(self) -> list[dict]:
        """获取浏览器实例统计信息"""
        async with self._lock:
            stats = []
            now = time.time()
            for key, browser in self._browsers.items():
                tab_count = len([t for t in browser.tabs if not t.closed])
                age = now - self._browser_start_times.get(key, now)
                stats.append({
                    "proxy": key,
                    "tabs": tab_count,
                    "age_seconds": round(age, 1),
                })
            return stats
