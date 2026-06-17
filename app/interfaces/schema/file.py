from typing import Optional

from pydantic import BaseModel, Field


class FileReadRequest(BaseModel):
    """读取文件内容的请求结构体"""

    filepath: str = Field(..., description="要读取文件的绝对路径")
    start_line: Optional[int] = Field(default=None, description="（可选）读取的起始行")
    end_line: Optional[int] = Field(default=None, description="（可选）结束行号")
    sudo: Optional[bool] = Field(default=None, description="（可选）是否使用 sudo 权限")
    max_length: Optional[int] = Field(default=10000, description="（可选）最大字符数")

class FileWriteRequest(BaseModel):
    """写入文件内容的请求结构体"""

    filepath: str = Field(..., description="要写入文件的绝对路径")
    content: str = Field(..., description="要写入文件的内容")
    append: bool = Field(default=False, description="（可选）是否使用追加模式")
    leading_newline: bool = Field(default=False, description="(可选) 是否在内容开头添加一个分隔符")
    trailing_newline: bool = Field(default=False, description="(可选) 是否在内容结尾添加一个分隔符")
    sudo: bool = Field(default=False, description="（可选）是否使用 sudo 权限")

class FileReplaceRequest(BaseModel):
    """查找替换文件内容的请求结构体"""

    filepath: str = Field(..., description="要替换内容的文件绝对路径")
    old_str: str = Field(..., description="要替换的原始字符串")
    new_str: str = Field(..., description="要替换的新字符串")
    sudo: Optional[bool] = Field(default=False, description="(可选) 是否使用 sudo 权限 ")

class FileSearchRequest(BaseModel):
    """文件内容查找请求结构体"""

    filepath: str = Field(..., description="要查找内容的文件绝对路径")
    regex: str = Field(..., description="搜索的正则表达式")
    sudo: Optional[bool] = Field(default=False, description="(可选)是否使用sudo权限")


class FileFindRequest(BaseModel):
    """文件查找请求结构体"""

    dir_path: str = Field(..., description="搜索的目录的绝对路径")
    glob_pattern: str = Field(..., description="文件名模式(glob)")

class FileCheckRequest(BaseModel):
    """检查文件是否存在请求结构体"""

    filepath: str = Field(..., description="要检查是否存在的文件路径")

class FileDeleteRequest(BaseModel):
    """删除文件请求结构体"""

    filepath: str = Field(..., description="要删除的文件绝对路径")
