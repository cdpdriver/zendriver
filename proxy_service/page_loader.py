"""
Page Loader - 页面加载器，处理 Cloudflare 验证和特殊页面状态
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zendriver import Tab

logger = logging.getLogger(__name__)


@dataclass
class CloudflareConfig:
    """Cloudflare 验证配置"""

    enabled: bool = True  # 是否启用 CF 验证
    max_retries: int = 3  # 最大重试次数
    click_delay: float = 2.0  # 点击间隔（秒）
    challenge_timeout: float = 15.0  # 验证超时（秒）
    check_interval: float = 0.5  # 检查间隔（秒）
    detect_timeout: float = 0.1  # 检测超时（秒）

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CloudflareConfig":
        """从字典创建配置"""
        if not data:
            return cls()
        return cls(
            enabled=data.get("enabled", True),
            max_retries=data.get("max_retries", 3),
            click_delay=data.get("click_delay", 2.0),
            challenge_timeout=data.get("challenge_timeout", 15.0),
            check_interval=data.get("check_interval", 0.5),
            detect_timeout=data.get("detect_timeout", 0.1),
        )


@dataclass
class PageLoadResult:
    """页面加载结果"""

    success: bool
    html: str
    final_url: str
    error: str | None = None

    # Cloudflare 状态
    cf_detected: bool = False
    cf_solved: bool = False
    cf_retries: int = 0

    # 页面状态: ok, queue, blocked, unreachable
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result: dict[str, Any] = {
            "success": self.success,
            "html": self.html,
            "url": self.final_url,
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


class PageLoader:
    """页面加载器，处理 CF 验证和特殊页面状态"""

    # 被阻止的页面文本
    BLOCKED_TEXTS = [
        "Please wait a few minutes and try again.",
        "Access denied",
        "You have been blocked",
    ]

    # 队列等待的页面文本
    QUEUE_TEXTS = [
        "To enter the queue",
        "You are in the queue",
        "Queue-it",
    ]

    # 无法访问的页面文本
    UNREACHABLE_TEXTS = [
        "This site can’t be reached",
        "ERR_CONNECTION_REFUSED",
        "ERR_NAME_NOT_RESOLVED",
        "ERR_CONNECTION_TIMED_OUT",
    ]

    async def load(
        self,
        tab: "Tab",
        url: str,
        wait_for: str | None = None,
        timeout: float = 30,
        cf_config: CloudflareConfig | None = None,
    ) -> PageLoadResult:
        """
        加载页面，处理 CF 验证

        Args:
            tab: 浏览器 Tab
            url: 目标 URL
            wait_for: 等待的 CSS 选择器
            timeout: 总超时时间（秒）
            cf_config: Cloudflare 配置

        Returns:
            PageLoadResult
        """
        from zendriver.core.cloudflare import cf_is_interactive_challenge_present

        cf_config = cf_config or CloudflareConfig()
        start_time = time.time()
        cf_detected = False
        cf_solved = False
        cf_retries = 0

        try:
            # 导航到 URL
            logger.info(f"Navigating to: {url}")
            await tab.get(url)

            while time.time() - start_time < timeout:
                elapsed = time.time() - start_time
                logger.debug(f"Page load loop, elapsed: {elapsed:.1f}s")

                # 1. 检测并解决 Cloudflare 挑战
                if cf_config.enabled:
                    try:
                        has_challenge = await cf_is_interactive_challenge_present(
                            tab, timeout=cf_config.detect_timeout
                        )
                        if has_challenge:
                            cf_detected = True
                            logger.info("Cloudflare challenge detected, solving...")

                            try:
                                await tab.verify_cf(
                                    click_delay=cf_config.click_delay,
                                    timeout=cf_config.challenge_timeout,
                                    flash_corners=False,
                                )
                                cf_solved = True
                                logger.info("Cloudflare challenge solved!")
                                # 解决后等待页面加载
                                await asyncio.sleep(1)
                                continue
                            except TimeoutError:
                                cf_retries += 1
                                logger.warning(
                                    f"CF challenge timeout, retry {cf_retries}/{cf_config.max_retries}"
                                )
                                if cf_retries >= cf_config.max_retries:
                                    return PageLoadResult(
                                        success=False,
                                        html=await self._safe_get_content(tab),
                                        final_url=tab.url or url,
                                        error=f"Cloudflare challenge failed after {cf_retries} retries",
                                        cf_detected=True,
                                        cf_solved=False,
                                        cf_retries=cf_retries,
                                    )
                                continue
                    except Exception as e:
                        logger.debug(f"CF detection error (ignored): {e}")

                # 2. 检测特殊页面状态
                status, status_msg = await self._check_page_status(tab)
                if status == "blocked":
                    logger.warning(f"Page blocked: {status_msg}")
                    return PageLoadResult(
                        success=False,
                        html=await self._safe_get_content(tab),
                        final_url=tab.url or url,
                        error=f"Page blocked: {status_msg}",
                        cf_detected=cf_detected,
                        cf_solved=cf_solved,
                        cf_retries=cf_retries,
                        status="blocked",
                    )
                elif status == "queue":
                    logger.info(f"In queue: {status_msg}")
                    return PageLoadResult(
                        success=False,
                        html=await self._safe_get_content(tab),
                        final_url=tab.url or url,
                        error=f"In queue: {status_msg}",
                        cf_detected=cf_detected,
                        cf_solved=cf_solved,
                        cf_retries=cf_retries,
                        status="queue",
                    )
                elif status == "unreachable":
                    logger.warning(f"Site unreachable: {status_msg}")
                    return PageLoadResult(
                        success=False,
                        html=await self._safe_get_content(tab),
                        final_url=tab.url or url,
                        error=f"Site unreachable: {status_msg}",
                        cf_detected=cf_detected,
                        cf_solved=cf_solved,
                        cf_retries=cf_retries,
                        status="unreachable",
                    )

                # 3. 检测目标元素
                if wait_for:
                    try:
                        elem = await tab.select(wait_for, timeout=0.1)
                        if elem:
                            logger.info(f"Target element found: {wait_for}")
                            return PageLoadResult(
                                success=True,
                                html=await self._safe_get_content(tab),
                                final_url=tab.url or url,
                                cf_detected=cf_detected,
                                cf_solved=cf_solved,
                                cf_retries=cf_retries,
                            )
                    except Exception:
                        pass  # 元素未找到，继续循环
                else:
                    # 无 wait_for，检查页面是否加载完成
                    try:
                        ready_state = await tab.evaluate("document.readyState")
                        if ready_state == "complete":
                            # 额外等待一小段时间确保 JS 执行完成
                            await asyncio.sleep(0.5)
                            logger.info("Page load complete (readyState=complete)")
                            return PageLoadResult(
                                success=True,
                                html=await self._safe_get_content(tab),
                                final_url=tab.url or url,
                                cf_detected=cf_detected,
                                cf_solved=cf_solved,
                                cf_retries=cf_retries,
                            )
                    except Exception:
                        pass

                await asyncio.sleep(cf_config.check_interval)

            # 超时
            logger.warning(f"Page load timeout after {timeout}s")
            return PageLoadResult(
                success=False,
                html=await self._safe_get_content(tab),
                final_url=tab.url or url,
                error=f"Timeout after {timeout}s",
                cf_detected=cf_detected,
                cf_solved=cf_solved,
                cf_retries=cf_retries,
            )

        except Exception as e:
            logger.exception(f"Page load error: {e}")
            return PageLoadResult(
                success=False,
                html=await self._safe_get_content(tab),
                final_url=tab.url or url,
                error=str(e),
                cf_detected=cf_detected,
                cf_solved=cf_solved,
                cf_retries=cf_retries,
            )

    async def _check_page_status(self, tab: "Tab") -> tuple[str, str]:
        """
        检查页面状态

        Returns:
            (status, message) - status: ok/blocked/queue/unreachable
        """
        try:
            text = await tab.evaluate("document.body ? document.body.innerText : ''")
            if not text:
                return "ok", ""

            # 检查被阻止
            for blocked in self.BLOCKED_TEXTS:
                if blocked in text:
                    return "blocked", blocked

            # 检查队列
            for queue in self.QUEUE_TEXTS:
                if queue in text:
                    return "queue", queue

            # 检查无法访问
            for unreachable in self.UNREACHABLE_TEXTS:
                if unreachable in text:
                    return "unreachable", unreachable

            return "ok", ""
        except Exception as e:
            logger.debug(f"Error checking page status: {e}")
            return "ok", ""

    async def _safe_get_content(self, tab: "Tab") -> str:
        """安全获取页面内容"""
        try:
            return await tab.get_content()
        except Exception as e:
            logger.warning(f"Failed to get page content: {e}")
            return ""
