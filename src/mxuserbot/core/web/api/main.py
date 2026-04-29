import os
import time
import asyncio
import subprocess

import uvicorn
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


def ensure_ssh():
    try:
        result = subprocess.run(['ssh', '-V'], capture_output=True, text=True)
        if result.returncode == 0:
            return True
        else:
            print("❌ SSH not found!")
            return False
    except Exception as e:
        print(f"❌ Error checking SSH: {e}")
        return False

async def run_web_server(mx, port: int):
    # Достаем значение из базы
    db_host = await mx._db.get("core", "host")

    # По умолчанию для локалки
    if "SHARKHOST" in os.environ or "DOCKER" in os.environ:
        bind_host = '0.0.0.0'
    else:
        bind_host = '127.0.0.1'

    public_url = None

    if db_host == "localhost":
        public_url = f"http://127.0.0.1:{port}"
        bind_host = "127.0.0.1"
        
    elif db_host == "0.0.0.0":
        public_url = f"http://0.0.0.0:{port}"
        bind_host = "0.0.0.0"
        
    elif db_host == "tunnel" or not db_host:
        mx.log.info("🌐 | Starting SSH tunnel...")
        tunnel_url = await get_public_url(port=port)
        if tunnel_url:
            public_url = tunnel_url
        else:
            public_url = f"http://{bind_host}:{port}"
            
    else:
        public_url = db_host

    app = FastAPI(title="Sekai Bot API")
    setup_routes(app, mx, mx.auth_completed)
    
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=bind_host,
            port=port,
            log_level="error"
        )
    )
    server.install_signal_handlers = lambda: None
    
    async def _serve_api():
        try:
            await server.serve()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
            
    asyncio.create_task(_serve_api())
    mx.log.info(f"🌐 | API local URL: http://{bind_host}:{port}")
    mx.log.info(f"🚀 | API Public URL: {public_url}")


async def get_public_url(port: int):
    if not ensure_ssh():
        return None

    localhost_run_output_file = "/tmp/localhost_run_output.txt"
    if os.path.exists(localhost_run_output_file):
        os.remove(localhost_run_output_file)

    try:      
        subprocess.Popen(
            f'ssh -o StrictHostKeyChecking=no -R 80:localhost:{port} nokey@localhost.run > {localhost_run_output_file} 2>&1 &',
            shell=True,
            preexec_fn=os.setsid
        )
        
        timeout = 10 
        start_time = time.time()
        while time.time() - start_time < timeout:
            if os.path.exists(localhost_run_output_file):
                with open(localhost_run_output_file, 'r') as file:
                    content = file.read()
                    lines = content.splitlines()
                    for line in lines:
                        if "tunneled with tls termination" in line:
                            url = line.split()[-1]
                            return url
            await asyncio.sleep(1)
            
        print("⏰ Timeout reached, no URL found")
        return None 
    except Exception as e:
        print(f"📝 Logging: Error starting localhost.run or getting public URL: {e}")
        return None