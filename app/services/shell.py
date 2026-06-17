import asyncio
import codecs
import getpass
import logging
import os
import re
import socket
import uuid
from typing import Dict, List, Optional

from app.interfaces.errors.exceptions import (
    AppException,
    BadRequestException,
    NotFoundException,
)
from app.models.shell import (
    ConsoleRecord,
    Shell,
    ShellExecuteResult,
    ShellKillResult,
    ShellReadResult,
    ShellWaitResult,
    ShellWriteResult,
)

logger = logging.getLogger(__name__)

ENCODING = "utf-8"

class ShellService:
    """Shell服务类"""

    active_shells: Dict[str, Shell] = {}

    _ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[0-?]*[ -/]*[@-~])")

    @classmethod
    def create_session_id(cls) -> str:
        """创建会话id,使用 uuid4 生成唯一键"""
        session_id = str(uuid.uuid4())
        logger.info(f"创建一个新的 Shell 会话 ID：{session_id}")
        return session_id

    @classmethod
    def _get_display_path(cls, path: str) -> str:
        """获取显示路径，将 ~ 替换成用户目录"""
        # 1.使用程序获取跨平台下用户的主目录
        home_dir = os.path.expanduser("~")
        logger.info(f"主目录: {home_dir}, 路径: {path}")

        # 2.判断传递进来的路径是否时主路径，如果是则替换成 ~
        if path.startswith(home_dir):
            return path.replace(home_dir, "~", 1)
        return path

    def _format_ps1(self, exec_dir: str) -> str:
        """格式化命令结构提示，增强交互体验，例如：root@cyrus:/var/log $"""
        username = getpass.getuser()
        hostname = socket.gethostname()
        display_dir = self._get_display_path(exec_dir)
        return f"{username}@{hostname}:{display_dir}"

    def _remove_ansi_escape_codes(self, raw_output: str) -> str:
        """从文本中移除 ANSI 转义码"""
        return self._ANSI_ESCAPE_PATTERN.sub("", raw_output)

    def get_console_records(self, session_id: str) -> List[ConsoleRecord]:
        """获取指定会话的控制台记录"""
        logger.info(f"正在获取 Shell 会话的控制台记录：{session_id}")
        if session_id not in self.active_shells:
            logger.error(f"Shell 会话不存在：{session_id}")
            raise NotFoundException(msg=f"Shell 会话不存在：{session_id}")

        # 2.获取原始的控制台记录列表
        console_records = self.active_shells[session_id].console_records
        clean_console_records = []

        # 3.执行循环处理所有的记录输出
        for console_record in console_records:
            clean_console_records.append(
                ConsoleRecord(
                    ps1=console_record.ps1,
                    command=console_record.command,
                    output=self._remove_ansi_escape_codes(console_record.output),
                )
            )

        return clean_console_records

    async def _create_process(
        self, exec_dir: str, command: str
    ) -> asyncio.subprocess.Process:
        """传递执行目录+命令 创建一个 asyncio 管理的子进程"""
        # 1.根据不同的系统选择不同的解释器
        logger.debug(f"在目录 {exec_dir} 下使用命令 {command} 创建一个子进程")
        shell_exec = "/bin/bash"

        # 2.创建一个系统级的子进程来执行 shell 命令
        return await asyncio.create_subprocess_shell(
            command,
            executable=shell_exec,
            cwd=exec_dir,
            stdout=asyncio.subprocess.PIPE,  # 创建管道以捕获标准输出
            stderr=asyncio.subprocess.STDOUT,  # 将标准错误重定向到标准输出流
            stdin=asyncio.subprocess.PIPE,  # 创建管道以允许标准输入
            limit=1024 * 1024,  # 设置缓冲区
        )

    async def _start_output_reader(
        self, session_id: str, process: asyncio.subprocess.Process
    ) -> None:
        """启动协程以连续读取进程输出，并将其存储到会话中"""
        # 1.动态确定系统编码
        logger.info(f"正在启动会话输出读取器：{session_id}")

        # 2.创建增量编码器(解决字符被切断的问题)
        decoder = codecs.getincrementaldecoder(encoding=ENCODING)(errors="replace")

        shell = self.active_shells.get(session_id)

        while True:
            # 3.判断子进程是否有标准输出管道
            if process.stdout:
                try:
                    # 4.读取缓存区的数据，假设一次读取 4096
                    buffer = await process.stdout.read(4096)
                    if not buffer:
                        break

                    # 5.使用编码器进行编码，同时设置 final=False 标识未结束
                    output = decoder.decode(buffer, final=False)

                    # 6.判断会话是否存在
                    if shell:
                        # 7.更新会话输出和控制台输出
                        shell.output += output
                        if shell.console_records:
                            shell.console_records[-1].output += output
                except Exception as e:
                    logger.error(f"读取进程输出时错误：{str(e)}")
                    break
            else:
                break

        final_text = decoder.decode(b"", final=True)
        if final_text and shell:
            shell.output += final_text
            if shell.console_records:
                shell.console_records[-1].output += final_text
        logger.debug(f"会话 {session_id} 的输出读取器已完成")

    async def wait_process(
        self, session_id: str, seconds: Optional[int] = None
    ) -> ShellWaitResult:
        """等待子进程执行完成，最多等待指定秒数"""
        # 1.判断 session_id 对应的会话是否存在
        logger.debug(f"正在Shell会话中等待进程：{session_id}, 超时时间:{seconds}")
        if session_id not in self.active_shells:
            logger.error(f"Shell会话不存在：{session_id}")
            raise NotFoundException(msg=f"Shell 会话不存在：{session_id}")

        # 2.获取会话和子进程
        shell = self.active_shells[session_id]
        process = shell.process

        try:
            # 3.判断是否设置 seconds
            seconds = 60 if seconds is None or seconds <= 0 else seconds
            await asyncio.wait_for(process.wait(), timeout=seconds)

            # 4.记录日志并返回等待结果
            logger.info(f"进程已完成，返回代码为：{process.returncode}")
            return ShellWaitResult(returncode=process.returncode)
        except asyncio.TimeoutError:
            # 记录日志并抛出 BadRequest 异常
            logger.error(f"Shell 会话进程等待超时：{seconds}s")
            raise BadRequestException(f"Shell 会话进程等待超时：{seconds}s")
        except Exception as e:
            # 记录日志并抛出 AppException
            logger.error(f"Shell会话进程等待过程出错：{str(e)}")
            raise AppException(f"Shell会话进程等待过程错误：{str(e)}")

    async def read_shell_output(
        self, session_id: str, console: bool = False
    ) -> ShellReadResult:
        """根据传递的会话 id + 是否输出控制台记录获取 Shell 命令结果"""
        # 1. 判断 session_id 对应的对话是否存在
        logger.info(f"查看 Shell 会话内容：{session_id}")
        if session_id not in self.active_shells:
            logger.info(f"会话不存在，session_id:{session_id}")
            raise NotFoundException(f"Shell 会话不存在：{session_id}")

        # 2.获取会话
        shell = self.active_shells[session_id]

        # 3.获取原生输出并移除额外字符
        raw_output = shell.output
        clean_output = self._remove_ansi_escape_codes(raw_output)

        # 4.判断是否获取控制台记录
        if console:
            console_records = self.get_console_records(session_id)
        else:
            console_records = []

        return ShellReadResult(
            session_id=session_id,
            output=clean_output,
            console_records=console_records,
        )

    async def exec_command(
        self, session_id: str, exec_dir: str, command: str
    ) -> ShellExecuteResult:
        """传递会话ID+执行目录+命令在沙箱中执行后返回"""
        # 1.记录日志并判断执行目录是否存在
        logger.info(f"正在会话 {session_id} 中执行命令：{command}")
        if not exec_dir or exec_dir == "":
            exec_dir = os.path.expanduser("~")
        if not os.path.exists(exec_dir):
            logger.error(f"当前目录不存在:  {exec_dir}")
            raise BadRequestException(f"当前目录不存在：{exec_dir}")

        # 格式化生成 ps1 格式
        ps1 = self._format_ps1(exec_dir=exec_dir)

        try:
            # 判断当前 Shell 会话是否存在
            if session_id not in self.active_shells:
                # 1.创建一个新的进程
                logger.info(f"开始创建一个新的 Shell 会话：{session_id}")
                process = await self._create_process(exec_dir, command)
                self.active_shells[session_id] = Shell(
                    process=process,
                    exec_dir=exec_dir,
                    output="",
                    console_records=[
                        ConsoleRecord(ps1=ps1, command=command, output="")
                    ],
                )
                # 创建后台任务来运行输出读取器
                asyncio.create_task(self._start_output_reader(session_id, process))
            else:
                # 该会话已经存在，则读取数据
                logger.debug(f"使用先有的 Shell 会话：{session_id}")
                shell = self.active_shells[session_id]
                old_process = shell.process

                # 判断旧进程是否还在运行，如果是则先停止旧进程再执行命令
                if old_process.returncode is None:
                    logger.debug(f"正在终止会话中上一个进程：{session_id}")
                    try:
                        # 结束旧进程并优化等待 1s
                        old_process.terminate()
                        await asyncio.wait_for(old_process.wait(), timeout=1)
                    except Exception as _:
                        # 结束旧进程出现错误，记录日志并调用 kill 强制结束
                        logger.warning(f"强制终止 Shell 会话中的进程：{session_id}")
                        old_process.kill()

                # 关闭后创建一个新的进程
                process = await self._create_process(exec_dir=exec_dir, command=command)

                # 更新会话信息-初始化状态
                shell.process = process
                shell.exec_dir = exec_dir
                shell.output = ""
                shell.console_records.append(
                    ConsoleRecord(ps1=ps1, command=command, output="")
                )

            # 开始读取数据
            try:
                # 尝试等待子进程执行（最多5s）
                logger.debug(f"正在等待会话中的进程完成: {session_id}")
                wait_result = await self.wait_process(session_id, seconds=5)

                # 判断返回的代码是否非空（已结束），则同步返回结果
                if wait_result.returncode is not None:
                    # 记录日志并查看结果
                    logger.debug(
                        f"会话中的进程已完成: {session_id}, 返回码: {wait_result.returncode}"
                    )
                    view_result = await self.read_shell_output(session_id=session_id)

                    return ShellExecuteResult(
                        session_id=session_id,
                        command=command,
                        status="completed",
                        returncode=wait_result.returncode,
                        output=view_result.output,
                    )
            except BadRequestException as _:
                # 等待超时，记录日志不做额外处理让命令在后台继续运行
                logger.warning(f"进程在会话超时后仍在运行：{session_id}")
                pass
            except Exception as e:
                # 其他异常忽略并让程序继续进行
                logger.warning(f"等待进程时出现异常：{str(e)}")
                pass

            return ShellExecuteResult(
                session_id=session_id, command=command, status="running"
            )
        except Exception as e:
            # 1.执行过程中出现异常并记录日志后返回自定义异常
            logger.error(f"命令执行失败：{str(e)},", exc_info=True)
            raise AppException(
                msg=f"命令执行失败：{str(e)}",
                data={"session_id": session_id, "command": command},
            )

    async def write_shell_input(
        self, 
        session_id: str, 
        input_text: str, 
        press_enter: bool
    ) -> ShellWriteResult:
        """根据传递的数据向指定子进程写入数据"""
        # 1.判断 session_id 对应的 Shell 是否存在
        logger.debug(f"写入Shell会话中的子进程：{session_id}, 是否按下回车键：{press_enter}")
        if session_id not in self.active_shells:
            logger.error(f"Shell 会话不存在：{session_id}")
            raise NotFoundException(f"Shell 会话不存在：{session_id}")

        # 2.获取会话和子进程
        shell = self.active_shells[session_id]
        process = shell.process

        try:
            # 3.检查子进程是否结束
            if process.returncode is not None:
                logger.error(f"子进程已经结束，无法写入输入：{session_id}")
                raise BadRequestException("子进程已结束，无法写入输入")

            # 确认系统编码
            line_ending = "\n"

            # 5.准备要发送的内容
            text_to_send = input_text
            if press_enter:
                text_to_send += line_ending

            # 6. 将字符串编码为字节流
            input_data = text_to_send.encode(encoding=ENCODING)

            # 7.记录日志
            log_text = input_text + ("\n" if press_enter else "")
            shell.output += log_text
            if shell.console_records:
                shell.console_records[-1].output += log_text

            # 8.向子进程写入数据
            process.stdin.write(input_data)
            await process.stdin.drain()

            # 9.记录日志并返回写入结果
            logger.info("成功向子进程写入数据")
            return ShellWriteResult(status="success")

        except UnicodeError as e:
            # 捕获编码异常
            logger.error(f"编码错误：{str(e)}")
            raise AppException(msg=f"编码错误：{str(e)}")
        except Exception as e:
            # 捕获通用异常
            logger.error(f"向子进程写入数据出错：{str(e)}")
            raise AppException(msg=f"向子进程写入数据出错：{str(e)}")
        
    async def kill_process(
        self, 
        session_id: str
    ) -> ShellKillResult:
        """根据传递的 session_id 关闭对应的进程"""
        # 1.判断 session_id 对应的 Shell 是否存在
        logger.debug(f"正在终止会话中的进程：{session_id}")
        if session_id not in self.active_shells:
            logger.error(f"Shell 会话不存在：{session_id}")
            raise NotFoundException(f"Shell 会话不存在：{session_id}")

        # 2.获取会话和子进程
        shell = self.active_shells[session_id]
        process = shell.process

        try:
            # 3.检查子进程是否还在运行
            if process.returncode is None:
                # 4.记录日志并尝试优雅关闭
                logger.info(f"尝试优雅终止进程：{session_id}")
                process.terminate()

                try:
                    # 5.等待3秒时间
                    await asyncio.wait_for(process.wait(), timeout=3)
                except Exception as _:
                    logger.error(f"尝试强制关闭进程：{session_id}")
                    process.kill()

                # 记录日志并返回关闭结果
                logger.info(f"进程已终止，返回代码：{process.returncode}")
                return ShellKillResult(status="terminated", returncode=process.returncode)
            else:
                # 进程已结束，无需重复关闭
                logger.info(f"进程已终止，返回代码为：{process.returncode}")
                return ShellKillResult(status="already_terminated", returncode=process.returncode)
        except Exception as e:
            # 记录日志并抛出异常
            logger.error(f"关闭进程失败：{str(e)}", exc_info=True)
            raise AppException(msg=f"关闭进程失败：{str(e)}")