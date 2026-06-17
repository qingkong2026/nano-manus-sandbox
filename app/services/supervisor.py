import asyncio
import http
import logging
import socket
import xmlrpc.client

from typing import List, Any

from app.interfaces.errors.exceptions import AppException
from app.models.supervisor import ProcessInfo

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

    def __init__(self) -> None:
        """构造函数，完成 Supervisor 服务连接"""
        self.rpc_url = "/tmp/supervisor.sock"
        self._connect_rpc()

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
            return await asyncio.to_thread(method, *args)
        except asyncio.TimeoutError:
            logger.error("RPC 调用超时")
            raise AppException(msg="Supervisor 调用超时")
        except (socket.error, xmlrpc.client.Fault) as e:
            logger.error(f"连接 Supervisor 失败: {e}")
            raise AppException(msg="Supervisor 服务不可用")
        except Exception as e:
            logger.error(f"RPC 方法调用失败：{str(e)}")
            raise AppException(msg=f"RPC 方法调用失败：{str(e)}")

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
