import asyncio
import http
import logging
import socket
from telnetlib import STATUS
import threading
import xmlrpc.client
from datetime import datetime, timedelta

from typing import List, Any, Optional

from app.interfaces.errors.exceptions import AppException, BadRequestException
from app.models.supervisor import ProcessInfo, SupervisorActionResult, SupervisorTimeoutResult
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class UnixStreamHTTPConnection(http.client.HTTPConnection):
    """基于 Unix 流的 HTTP 连接处理器"""

    def __init__(self, host: str , socket_path: str ,timeout: float | None = None) -> None:
        super().__init__(host,timeout=timeout)
        self.socket_path = socket_path
        self.sock = None

    def connect(self)-> None:
        """重写连接方法, 欺骗 xml-rpc 库,让其觉得自己正在进行网络连接"""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.timeout is not None:
            sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock

class UnixStreamTransport(xmlrpc.client.Transport):
    """基于 Unix 流传输层的适配器/转换器"""

    def __init__(self, socket_path: str) -> None:
        """构造函数，完成传输适配器的初始化"""
        super().__init__()
        self.socket_path = socket_path

    def make_connection(self, host) -> http.client.HTTPConnection:
        return UnixStreamHTTPConnection(host, self.socket_path, timeout=10.0)


class SupervisorService:
    """Supervisor 服务端"""

    RPC_TIMEOUT = 10
    GROUP_NAME = "services"

    def __init__(self) -> None:
        """构造函数，完成 Supervisor 服务连接"""
        self.rpc_url = "/tmp/supervisor.sock"
        self._connect_rpc()

        # 2.supervisor 超时配置
        settings: Settings = get_settings()
        self.timeout_active = settings.server_timeout_minutes is not None
        self.shutdown_task = None
        self.shutdown_time = None
        self._expand_enabled = True # 是否自动保活(每调用一次接口就增加时间)

        # 3.检测是否配置了自动销毁
        if settings.server_timeout_minutes is not None:
            # 4.设置销毁时间 + 定时器
            self.shutdown_time = datetime.now() + timedelta(minutes=settings.server_timeout_minutes)
            self._setup_timer(settings.server_timeout_minutes)
        
    @property
    def expand_enabled(self) -> None:
        """read-only, 返回是否自动保活"""
        return self._expand_enabled

    def enable_expand(self) -> None:
        """开启自动保活"""
        self._expand_enabled = True
    
    def disable_expand(self) -> None:
        """关闭自动保活"""
        self._expand_enabled = False

    def _setup_timer(self, minutes: int ) -> None:
        """传递时间并创建定时器，在时间结束后关闭 supervisord 主进程"""
        # 1.检测当前是否存在销毁任务，如果存在则先取消
        if self.shutdown_task:
            try:
                self.shutdown_task.cancel()
            except Exception as e:
                logger.error(f"取消shutdown任务失败: {str(e)}")
        
        # 2.创建一个异步定时器任务函数
        async def shutdown_after_timeout():
            await asyncio.sleep(minutes * 60)
            await self.shutdown()

        try:
            # 3.获取事件循环并添加任务
            loop = asyncio.get_event_loop()
            self.shutdown_task = loop.create_task(shutdown_after_timeout())
        except Exception as e:
            # 4.如果事件循环失败则创建一个新的线程来执行定时器
            if hasattr(self, "shutdown_timer") and self.shutdown_task:
                self.shutdown_timer.cancel()
            
            # 5.使用线程创建定时器并设置后台运行
            self.shutdown_timer = threading.Timer(
                minutes * 60,
                lambda: asyncio.run(self.shutdown())
            )
            self.shutdown_timer.daemon = True
            self.shutdown_timer.start()


    def _connect_rpc(self) -> None:
        """使用 python 的 xml-rpc 客户端连接一个本地 sock 文件实现连接 rpc 服务"""
        self.server = xmlrpc.client.ServerProxy(
            uri="http://localhost",
            transport=UnixStreamTransport(self.rpc_url),
        )

    @classmethod
    async def _call_rpc(cls, method, *args) -> Any:
        """根据传递的方法+参数调用rpc方法"""
        try:
            res = await asyncio.wait_for(
                asyncio.to_thread(method, *args),
                timeout=cls.RPC_TIMEOUT
            )
            return res
        except asyncio.TimeoutError:
            logger.error("RPC 调用超时")
            raise AppException(msg="Supervisor 调用超时")
        except (socket.error, xmlrpc.client.Fault) as e:
            logger.error(f"连接 Supervisor 失败: {e}")
            raise AppException(msg="Supervisor 服务不可用")
        except Exception as e:
            logger.error(f"RPC 未知失败：{str(e)}", exc_info=True)
            raise AppException(msg=f"RPC调用失败: {str(e)}")

    async def get_all_processes(self) -> List[ProcessInfo]:
        """获取沙箱中所有进程服务的状态信息"""
        try:
            process_list = await self._call_rpc(self.server.supervisor.getAllProcessInfo)
        except Exception as e:
            raise

        results = []
        for p in process_list or []:
            try:
                results.append(ProcessInfo(**p))
            except (TypeError, ValueError) as e:
                logger.warning(f"进程数据格式异常，已跳过：{p}, err={e}")
        return results

    async def stop_all_process(self) -> SupervisorActionResult:
        """停止沙箱中Supervisor管理的所有进程服务"""
        try:
            result = await self._call_rpc(self.server.supervisor.stopProcessGroup, self.GROUP_NAME , False)
            return SupervisorActionResult(status="stopped", result=result)
        except Exception as e:
            raise

    async def shutdown(self) -> SupervisorActionResult:
        """关闭沙箱中Supervisor服务"""
        try:
            result = await self._call_rpc(self.server.supervisor.shutdown)
            return SupervisorActionResult(status="shutdown", shutdown_result=result)
        except Exception as e:
            raise

    async def restart(self) -> SupervisorActionResult:
        """重启沙箱中Supervisor服务"""
        try:
            stop_result = await self._call_rpc(self.server.supervisor.stopProcessGroup, self.GROUP_NAME , False)
            start_result = await self._call_rpc(self.server.supervisor.stopProcessGroup, self.GROUP_NAME, False)
            return SupervisorActionResult(status="restarted", stop_result=stop_result , start_result=start_result)
        except Exception as e:
            raise

    
    async def activate_timeout(self, minutes: Optional[int] = None) -> SupervisorTimeoutResult:
        """传递指定分钟，并激活定时销毁任务同时关闭自动保活"""
        # 1.获取超时分钟数
        settings = get_settings()
        timeout_minutes = minutes or settings.server_timeout_minutes
        if timeout_minutes is None:
            raise BadRequestException("超时时间未配置，并且未读取到系统默认超时时间")

        # 2.更新超时配置
        self.timeout_active = True
        self.shutdown_time = datetime.now() + timedelta(minutes=timeout_minutes)

        # 3.创建一个新的定时器
        self._setup_timer(timeout_minutes)

        return SupervisorTimeoutResult(
            status="timeout_activated",
            active=True,
            shutdown_time=self.shutdown_time.isoformat(),
            timeout_minutes=timeout_minutes,
            remaining_seconds=(self.shutdown_time - datetime.now()).total_seconds()
        )
    
    async def extend_timeout(self, minutes: Optional[int] = 3) -> SupervisorTimeoutResult:
        """传递指定的时长,延长超时销毁的时间,默认延长3分钟"""
        # 1.获取超时分钟数
        if minutes is None:
            raise BadRequestException("超时时间未配置，请核实后重试")
        remaining = self.shutdown_time - datetime.now()
        timeout_minutes = round(max(0, remaining.total_seconds()) / 60) + minutes

        # 2.更新超时配置
        self.timeout_active = True
        self.shutdown_time = datetime.now() + timedelta(minutes=timeout_minutes)

        # 3.创建一个新的定时器
        self._setup_timer(timeout_minutes)

        return SupervisorTimeoutResult(
            status="timeout_extended",
            active=True,
            shutdown_time=self.shutdown_time.isoformat(),
            timeout_minutes=timeout_minutes,
        )


    async def cancel_timeout(self) -> SupervisorTimeoutResult:
        """取消超时销毁设置"""
        # 1.判断是否设置了超时销毁
        if not self.timeout_active:
            return SupervisorTimeoutResult(status="no_timeout_active", activate=False)
        
        # 2.取消销毁任务
        if self.shutdown_task:
            try:
                self.shutdown_task.cancel()
                self.shutdown_task = None
            except Exception as e:
                logger.warning(f"取消 shutdown 任务失败：{str(e)}")

        # 3.同步检测是否有定时器
        if hasattr(self, "shutdown_timer") and self.shutdown_timer:
            self.shutdown_timer.cancel()
            self.shutdown_timer = None

    async def get_timeout_status(self) -> SupervisorTimeoutResult:
        """获取当前 Supervisor 的超时状态"""
        # 1.判断是否开启超时销毁功能
        if not self.timeout_active:
            return SupervisorTimeoutResult(active=False)

        # 2.统计剩余秒数
        remaining_seconds = 0
        if self.shutdown_time:
            remaining = self.shutdown_time - datetime.now()
            remaining_seconds = max(0, remaining.total_seconds())
        
        return SupervisorTimeoutResult(
            active=self.timeout_active,
            shutdown_time=self.shutdown_time.isoformat() if self.shutdown_time  else None,
            remaining_seconds=remaining_seconds,
        )
