from pydantic import BaseModel, Field


class ProcessInfo(BaseModel):
    """进程信息模型"""

    name:str = Field(..., description="进程名字")
    group: str = Field(..., description="进程分组")
    description: str = Field(..., description="进程描述")
    start: int = Field(..., description="进程开始时间戳")
    end: int  = Field(..., description="进程结束时间戳")
    now: int = Field(..., description="当前时间戳")
    state: int = Field(..., description="状态代码")
    statename: str = Field(..., description="状态名字")
    spawnerr: str = Field(..., description="Spawn错误")
    existstatus: int = Field(..., description="退出状态")
    logfile: str = Field(..., description="日志文件")
    stdout_logfile: str = Field(..., description="标准输出日志文件")
    stderr_logfile: str = Field(..., description="标准错误日志文件")
    pid: int = Field(..., description="进程id(Process ID)")