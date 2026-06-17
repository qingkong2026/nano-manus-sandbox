import logging
from typing import Any

from fastapi import status

logger = logging.getLogger(__name__)


class AppException(RuntimeError):
    """应用基础异常"""

    def __init__(
        self,
        msg: str = "应用发生错误，请稍后重试",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        data: Any = None,
    ):
        self.msg = msg
        self.status_code = status_code
        self.data = data

        logger.error(f"Sandbox AppException: msg={msg}, status_code={status_code}")
        super().__init__(self.msg)


class NotFoundException(AppException):
    """资源未找到异常"""

    def __init__(
        self,
        msg: str = "资源未找到，稍后重试",
        status_code: int = status.HTTP_404_NOT_FOUND,
    ):
        super().__init__(msg, status_code)


class BadRequestException(AppException):
    """错误请求异常"""

    def __init__(
        self,
        msg: str = "客户端请求错误，稍后重试",
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ):
        super().__init__(msg, status_code)
