import logging
import sys

from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.interfaces.endpoints.routes import router
from app.interfaces.errors.exception_handler import register_exception_handler


def setup_logging():
    """配置 nano-manus 沙箱项目的日志系统，涵盖日志等级，输出格式，输出渠道等"""

    # 1.获取项目配置
    settings = get_settings()

    # 2.获取根日志处理器
    root_logger = logging.getLogger()

    # 3.设置日志级别
    log_level = getattr(logging, settings.log_level)
    root_logger.setLevel(log_level)

    # 4.日志输出格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 5.日志输出渠道
    consol_handler = logging.StreamHandler(sys.stdout)
    consol_handler.setFormatter(formatter)
    consol_handler.setLevel(log_level)

    # 6.将日志处理器添加到根日志处理器中
    root_logger.addHandler(consol_handler)

    root_logger.info("Sandbox system logging module initialized successfully.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager."""

    logger.info("nano-manus sandbox system startup.")
    try:
        yield
    finally:
        logger.info("nano-manus sandbox system shutdown successfully.")

# 1.初始化日志系统
setup_logging()
logger = logging.getLogger(__name__)

openapi_tags = [
    {
        "name": "文件模型",
        "description": "包含 **文件增删改查** 等 API 接口，用于实现沙箱文件的操作",
    },
    {
        "name": "Shell模块",
        "description": "包含 **执行/查看Shell** 等API接口，用于实现沙箱Shell的操作",
    },
    {
        "name": "Supervisor模块",
        "description": "使用接口+Supervisor 实现管理沙箱系统的程序逻辑",
    }
]

# 实例化 FastAPI 应用
app = FastAPI(
    title="nano-manus Sandbox System",
    description="该沙箱系统中预装了 Chrome、Python、Node.js、支持 Shell 命令执行，文件管理等",
    openapi_tags=openapi_tags,
    lifespan=lifespan,
    version="1.0.0",
)

# 添加 CORS 中间键
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册异常处理器
register_exception_handler(app)

# 集成路由
app.include_router(router,prefix="/api")