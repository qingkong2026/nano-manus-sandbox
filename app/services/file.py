import asyncio
import logging
import os
import re
import tempfile
import glob
from typing import Optional

from fastapi import UploadFile

from app.interfaces.errors.exceptions import (
    AppException,
    BadRequestException,
    NotFoundException,
)
from app.models.file import FileReadResult, FileWriteResult, FileReplaceResult, FileSearchResult, FileFindResult, \
    FileUploadResult, FileCheckResult, FileDeleteResult

logger = logging.getLogger(__name__)

DEFAULT_ENCODING = "utf-8"

class FileService:
    """File 服务类"""

    def __init__(self):
        pass


    @classmethod
    async def read_file(
        cls,
        filepath: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        sudo: Optional[bool] = False,
        max_length: Optional[int] = 10000,
    ) -> FileReadResult:
        """根据传递的文件路径+起始行号+权限+最大长度读取文件内容"""
        try:
            # 1.检测在当前权限下能否获取该文件
            if not os.path.exists(filepath) and not sudo:
                raise NotFoundException(
                    msg=f"要读取的文件不存在或无权限读取该文件：{filepath}"
                )

            # 3,判断是否为 sudo + 非 windows 系统，如果是则使用命令行的方式读取文件
            if sudo:
                # 4.使用 sudo cat 命令读取文件内容（参数化形式，避免 shell 注入）
                process = await asyncio.create_subprocess_exec(
                    "sudo", "cat", "--", filepath,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                # 5.读取子进程的输出，并等待子进程结束
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.communicate()
                    raise BadRequestException("读取文件超时，请检查 sudo 配置")
                
                # 6.判断子进程状态是否正常结束
                if process.returncode != 0:
                    raise BadRequestException(f"阅读文件失败：{stderr.decode()}")

                # 7.读取输出内容
                content = stdout.decode(DEFAULT_ENCODING, errors="replace")

            else:
                # 8. win32 环境下，使用 python 的函数读取文件内容
                def async_read_file() -> str:
                    try:
                        with open(filepath, "r", encoding=DEFAULT_ENCODING, errors="replace") as f:
                            return f.read()
                    except PermissionError:
                        raise BadRequestException(msg=f"无权限读取文件: {filepath}")
                    except Exception as async_read_file_exception:
                        raise AppException(msg=f"读取文件失败，{str(async_read_file_exception)}")

                # 9.使用 asyncio 创建线程读取文件
                content = await asyncio.to_thread(async_read_file)

            # 10.判断是否传递了读取范围
            if start_line is not None or end_line is not None:
                # 11.将内容切割成行，并且提取指定范围行号的数据
                lines = content.splitlines()
                start = start_line if start_line is not None else 0
                end = end_line if end_line is not None else len(lines)
                content = "\n".join(lines[start:end])

            # 12.裁剪下数据长度
            if max_length is not None and 0 < max_length < len(content):
                content = content[:max_length] + "(truncated)"

            return FileReadResult(filepath=filepath, content=content)
        except Exception as e:
            if isinstance(e, BadRequestException) or isinstance(e, AppException):
                raise
            raise AppException(f"文件读取失败：{str(e)}")

    @classmethod
    async def write_file(
        cls,
        filepath: str,
        content: str,
        append: bool = False,
        leading_newline: bool = False,
        trailing_newline: bool = False,
        sudo: bool = False,
    ) -> FileWriteResult:
        """根据传递的文件路径+内容向指定文件写入内容"""
        try:
            # 1.组装实际写入的内容
            if leading_newline:
                content = "\n" + content
            if trailing_newline:
                content = content + "\n"

            # 判断是否是 sudo 权限
            if sudo:
                # 2.创建一个临时文件（使用 tempfile 生成唯一随机文件名，避免并发冲突）
                fd, temp_file = tempfile.mkstemp(prefix="file_write_", suffix=".tmp")
                os.close(fd)

                try:
                    # 3.创建一个内部函数使用 asyncio 创建新线程写入数据
                    def async_write_temp_file() -> int:
                        with open(temp_file, "w", encoding=DEFAULT_ENCODING) as f:
                            f.write(content)
                        return len(content.encode(encoding=DEFAULT_ENCODING))

                    # 4.使用 asyncio 创建子线程
                    bytes_written = await asyncio.to_thread(async_write_temp_file)

                    # 5.使用 sudo tee 将临时文件写入目录文件
                    #    （参数化形式 + 用文件对象做 stdin，规避 shell 注入）
                    tee_args = ["sudo", "tee"]
                    if append:
                        tee_args.append("-a")
                    tee_args.extend(["--", filepath])
                    with open(temp_file, "rb") as stdin_file:
                        process = await asyncio.create_subprocess_exec(
                            *tee_args,
                            stdin=stdin_file,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.PIPE,
                        )

                    # 6.等待子进程执行完毕
                    try:
                        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
                    except Exception:
                        process.kill()
                        await process.communicate()
                        raise  BadRequestException("写入文件超时，请检查 sudo 配置")

                    # 7.检测子进程是否正常执行
                    if process.returncode != 0:
                        raise BadRequestException(f"文件内容写入失败：{stderr.decode()}")
                finally:
                    # 8.无论成功失败都清除临时文件
                    try:
                        os.unlink(temp_file)
                    except FileNotFoundError:
                        pass
            else:
                # 1.非 sudo 或者 windows 下使用 Python 方法写入文件
                parent_dir = os.path.dirname(filepath)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)

                # 2. 创建一个异步写入的函数
                def async_write_file() -> int:
                    write_mode = "a" if append else "w"
                    with open(filepath, write_mode, encoding=DEFAULT_ENCODING) as f:
                        return f.write(content)

                bytes_written = await asyncio.to_thread(async_write_file)

            return FileWriteResult(filepath=filepath, bytes_written=bytes_written)

        except Exception as e:
            # 根据不同的错误执行不同的逻辑
            if isinstance(e, BadRequestException):
                raise
            raise AppException(f"文件内容写入失败：{str(e)}")

    async def replace_in_file(
            self,
            filepath: str,
            old_str: str,
            new_str: str,
            sudo: bool = False,
    ) -> FileReplaceResult:
        """"""
        # 1.调用服务获取对应的文件内容
        file_read_result = await self.read_file(filepath=filepath, sudo=sudo)
        content = file_read_result.content

        # 2.计算 old_str 出现的次数
        replaced_count = content.count(old_str)
        if replaced_count == 0:
            return FileReplaceResult(filepath=filepath, replaced_count=replaced_count)

        # 3.替换旧内容
        new_content = content.replace(old_str, new_str)

        # 4.将替换后的内容重新写入文件中
        await self.write_file(
            filepath=filepath,
            content=new_content,
            sudo=sudo,
        )

        return FileReplaceResult(filepath=filepath, replaced_count=replaced_count)

    async def search_in_file(
            self, filepath: str, regex: str, sudo: bool = False
    ) -> FileSearchResult:
        """"""
        # 1.读取文件的内容
        file_read_result = await self.read_file(filepath=filepath, sudo=sudo)
        content = file_read_result.content

        # 2.将读取的内容拆分成一行
        lines = content.splitlines()
        matches = []
        line_numbers = []

        # 3.将外部传递的 regex 转为正则
        try:
            pattern = re.compile(regex)
        except Exception as e:
            raise BadRequestException(f"传递正则表达式解析出错：{str(e)}")

        # 4.创建一个异步函数，使用子线程执行避免长时间 io 阻塞
        def async_matches():
            nonlocal matches , line_numbers
            for idx, line in enumerate(lines):
                if pattern.match(line):
                    matches.append(line)
                    line_numbers.append(idx)

        # 5.使用 asyncio 创建子线程并调用
        await asyncio.to_thread(async_matches)

        return FileSearchResult(
            filepath=filepath,
            matches=matches,
            line_numbers=line_numbers,
        )

    @classmethod
    async def find_files(cls, dir_path: str, glob_pattern: str) -> FileFindResult:
        """根据传递的文件夹路径+glob规则查询文件列表"""
        # 1.检测下传递的目录路径是否存在
        if not os.path.exists(dir_path):
            raise NotFoundException(f"当前文件夹不存在，{dir_path}")

        # 2.定义一个异步函数使用 asyncio 子线程运行避免 IO 阻塞
        def async_glob():
            search_pattern = os.path.join(dir_path, glob_pattern)
            return glob.glob(search_pattern, recursive=True)

        # 3.创建子线程运行任务
        files = await asyncio.to_thread(async_glob)

        return FileFindResult(
            dir_path=dir_path,
            files=files,
        )

    @classmethod
    async def upload_file(cls, file: UploadFile, filepath: str) -> FileUploadResult:
        """根据传递的文件源 + 路径将文件上传至沙箱"""
        try:
            # 1.定义分块上传，每次只上传 8k
            chunk_size = 1024 * 8
            file_size = 0

            # 2.确保上传的文件所在耳朵目录存在
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # 3.定义一个异步函数用于上船文件
            def async_write_file():
                nonlocal file_size
                with open(filepath, mode="wb") as f:
                    while True:
                        chunk = file.file.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        file_size += len(chunk)

            # 4.使用子线程运行任务
            await asyncio.to_thread(async_write_file)

            return FileUploadResult(
                filepath=filepath,
                file_size=file_size,
                success=True,
            )

        except Exception as e:
            logger.error(f"上传文件到沙箱出现异常：{str(e)}")
            raise AppException(f"上传文件到沙箱出现异常：{str(e)}")

    @classmethod
    async def ensure_file(cls, filepath: str):
        """确保 filepath 路径下的文件存在"""
        if not os.path.exists(filepath):
            raise NotFoundException(f"该文件不存在")

    @classmethod
    async def check_file_exists(cls, filepath: str) -> FileCheckResult:
        return FileCheckResult(
            filepath=filepath,
            exists=os.path.exists(filepath),
        )

    async def delete_file(self, filepath: str) -> FileDeleteResult:
        """根据传递的路径 + sudo 删除指定的文件"""
        # 1.判断文件是否存在
        await self.ensure_file(filepath=filepath)

        try:
            # 2.调用命令
            os.remove(filepath)
            return FileDeleteResult(filepath=filepath, deleted=True)
        except Exception as e:
            logger.error(f"删除文件失败，{str(e)}")
            raise AppException(f"删除文件失败，{str(e)}")