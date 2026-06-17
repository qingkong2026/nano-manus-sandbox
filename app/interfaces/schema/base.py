from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Response(BaseModel, Generic[T]):
    """
    基础API响应结构,继承 BaseModel,并定义泛型
    """

    code: int = 200
    msg: str = "success"
    data: Optional[T] = Field(default_factory=dict)

    @staticmethod
    def success(msg: str = "success", data: Optional[T] = None) -> "Response[T]":
        return Response(code=200, msg=msg, data=data if data else {})

    @staticmethod
    def error(code: int, msg: str = "error", data: Optional[T] = None) -> "Response[T]":
        return Response(code=code, msg=msg, data=data if data else {})
