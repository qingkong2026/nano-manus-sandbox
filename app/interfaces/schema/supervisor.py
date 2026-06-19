from email.policy import default
from typing import Optional

from pydantic import BaseModel, Field

class TimeoutRequest(BaseModel):
    """激活超时销毁请求的模型"""

    minutes: Optional[int] = Field(default=None, description="分钟数")
    