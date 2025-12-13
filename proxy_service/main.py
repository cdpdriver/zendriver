"""
Proxy Service - FastAPI 入口

使用方式:
    uvicorn proxy_service.main:app --host 0.0.0.0 --port 8000

或者直接运行:
    python -m proxy_service.main
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .browser_pool import BrowserPool
from .cookie_manager import CookieManager
from .fetcher import Fetcher

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 配置
MAX_CONCURRENT = 5  # 最大并发数
DEFAULT_TIMEOUT = 30  # 默认超时（秒）
HEADLESS = True  # 无头模式


# 全局实例
browser_pool: BrowserPool | None = None
cookie_manager: CookieManager | None = None
fetcher: Fetcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global browser_pool, cookie_manager, fetcher

    # 启动时
    logger.info("Starting proxy service...")
    browser_pool = BrowserPool(max_concurrent=MAX_CONCURRENT, headless=HEADLESS)
    cookie_manager = CookieManager()
    fetcher = Fetcher(
        browser_pool=browser_pool,
        cookie_manager=cookie_manager,
        default_timeout=DEFAULT_TIMEOUT,
    )

    # 预启动浏览器
    await browser_pool.start()
    logger.info("Proxy service started")

    yield

    # 关闭时
    logger.info("Stopping proxy service...")
    await browser_pool.stop()
    logger.info("Proxy service stopped")


app = FastAPI(
    title="Zendriver Proxy Service",
    description="简单的浏览器代理服务，支持多并发、Cookie 管理、元素等待",
    version="0.1.0",
    lifespan=lifespan,
)


# 请求/响应模型
class FetchRequest(BaseModel):
    """抓取请求"""

    url: str = Field(..., description="目标 URL")
    wait_for: str | None = Field(None, description="等待的 CSS 选择器")
    timeout: float | None = Field(None, description="超时时间（秒），默认 30")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://example.com",
                    "wait_for": "#main-content",
                    "timeout": 20,
                }
            ]
        }
    }


class FetchResponse(BaseModel):
    """抓取响应"""

    success: bool = Field(..., description="是否成功")
    html: str = Field(..., description="页面 HTML")
    url: str = Field(..., description="最终 URL（可能有重定向）")
    elapsed: float = Field(..., description="耗时（秒）")
    error: str | None = Field(None, description="错误信息")


class StatusResponse(BaseModel):
    """状态响应"""

    status: str
    max_concurrent: int
    headless: bool
    cookie_domains: list[str]


# API 端点
@app.post("/fetch", response_model=FetchResponse)
async def fetch_page(request: FetchRequest) -> dict[str, Any]:
    """
    抓取页面 HTML

    - **url**: 目标 URL
    - **wait_for**: 等待的 CSS 选择器（可选）
    - **timeout**: 超时时间，默认 30 秒
    """
    if not fetcher:
        raise HTTPException(status_code=503, detail="Service not ready")

    result = await fetcher.fetch(
        url=request.url,
        wait_for=request.wait_for,
        timeout=request.timeout,
    )
    return result.to_dict()


@app.get("/status", response_model=StatusResponse)
async def get_status() -> dict[str, Any]:
    """获取服务状态"""
    if not browser_pool or not cookie_manager:
        raise HTTPException(status_code=503, detail="Service not ready")

    domains = await cookie_manager.list_domains()
    return {
        "status": "running" if browser_pool.is_started else "stopped",
        "max_concurrent": browser_pool.max_concurrent,
        "headless": browser_pool.headless,
        "cookie_domains": domains,
    }


@app.delete("/cookies")
async def clear_cookies(domain: str | None = None) -> dict[str, str]:
    """
    清除 Cookies

    - **domain**: 指定域名，不传则清除所有
    """
    if not cookie_manager:
        raise HTTPException(status_code=503, detail="Service not ready")

    if domain:
        await cookie_manager.clear_cookies(f"https://{domain}")
        return {"message": f"Cookies cleared for {domain}"}
    else:
        await cookie_manager.clear_cookies()
        return {"message": "All cookies cleared"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    """健康检查"""
    return {"status": "ok"}


# 直接运行入口
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "proxy_service.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
