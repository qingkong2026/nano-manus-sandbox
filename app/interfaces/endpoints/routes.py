from fastapi import APIRouter
from . import file, shell, supervisor

def create_api_routes() -> APIRouter:
    """创建API路由，涵盖整个沙箱项目的所有 API"""
    api_router = APIRouter()

    api_router.include_router(file.router)
    api_router.include_router(shell.router)
    api_router.include_router(supervisor.router)

    return api_router

router = create_api_routes()
