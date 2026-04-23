import asyncio

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from .constants import ASSETS_DIR, STATIC_DIR
from .context import APIContext
from .controllers import AuthController, ModuleController, PageController, RepoController, SystemController
from .dependencies import APIDependencies
from .schemas import (
    ConfigUpdateRequest,
    InstallRequest,
    LoginSchema,
    PrefixRequest,
    RepoActionRequest,
    UninstallRequest,
)
from .services import AuthService

__all__ = [
    "APIDependencies",
    "AuthService",
    "ConfigUpdateRequest",
    "InstallRequest",
    "LoginSchema",
    "PrefixRequest",
    "RepoActionRequest",
    "UninstallRequest",
    "build_routers",
    "setup_routes",
]


def build_routers(
    deps: APIDependencies,
    auth_event: asyncio.Event
) -> APIRouter:
    router = APIRouter()
    context = APIContext(mx=deps.mx, auth_event=auth_event)

    PageController(context).register(router)
    AuthController(context).register(router)
    SystemController(context, deps).register(router)
    ModuleController(context, deps).register(router)
    RepoController(context, deps).register(router)

    return router


def setup_routes(
    app: FastAPI,
    mx,
    auth_event: asyncio.Event
) -> None:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

    deps = APIDependencies(mx)
    app.include_router(build_routers(deps, auth_event))
