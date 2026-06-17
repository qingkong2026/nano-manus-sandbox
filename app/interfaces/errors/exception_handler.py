import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.interfaces.errors.exceptions import AppException
from app.interfaces.schema.base import Response

logger = logging.getLogger(__name__)


def register_exception_handler(app: FastAPI):

    @app.exception_handler(AppException)
    async def app_exception_handler(req: Request, e: AppException) -> JSONResponse:
        """处理 nano-manus 沙箱自定义业务异常，将所有状态统一响应结构"""
        logger.error(f"AppException: msg={e.msg}")
        return JSONResponse(
            status_code=e.status_code,
            content=Response(code=e.status_code, msg=e.msg, data={}).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(req: Request, e: HTTPException) -> JSONResponse:
        """处理 HTTP 异常，将所有状态统一响应结构"""
        logger.error(f"HTTPException: detail={e.detail}")
        return JSONResponse(
            status_code=e.status_code,
            content=Response(code=e.status_code, msg=str(e.detail), data={}).model_dump(),
        )

    @app.exception_handler(Exception)
    async def exception_handler(req: Request, e: Exception) -> JSONResponse:
        """处理其他异常，将所有状态统一响应结构"""
        logger.error(f"Exception: detail={e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=Response(
                code=status.HTTP_500_INTERNAL_SERVER_ERROR, msg=str(e), data={}
            ).model_dump(),
        )
