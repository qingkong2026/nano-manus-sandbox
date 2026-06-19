import logging

from app.core.config import get_settings
from app.interfaces.service_dependencies import get_supervisor_service
from app.models import supervisor
from fastapi import Request

logger = logging.getLogger(__name__)

async def auto_extend_timeout_middleware(request: Request, call_next):
    """使用中间件，每次 API 请求都延长超时销毁时间"""
    # 1.获取系统配置与 supervisor 服务
    settings = get_settings()
    supervisor_service = get_supervisor_service()

    # 2.判断逻辑，仅在符合条件时延长超时销毁时间，默认 3 分钟
    ignore_paths = (
        "/api/supervisor/activate-timeout",
        "/api/supervisor/extend-timeout",
        "/api/supervisor/cancel-timeout",
        "/api/supervisor/timeout-status",
    )

    if(
        settings.server_timeout_minutes is not None 
        and supervisor_service.timeout_active
        and request.url.path.startswith("/api")
        and not request.url.path.startswith(ignore_paths)
        and supervisor_service.expand_enabled
    ):
        try:
            await supervisor_service.extend_timeout(3)
            logger.debug("调用API请求,自动延长超时销毁时长：%s",request.url.path)
        except Exception as e:
            logger.warning("自动延长超时失败：%s", str(e))

    response = await call_next(request)

    return response
    
