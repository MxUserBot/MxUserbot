# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from fastapi import APIRouter, Depends

from ..context import APIContext
from ..dependencies import APIDependencies
from ..schemas import HostRequest, PrefixRequest


class SystemController:
    def __init__(self, context: APIContext, deps: APIDependencies) -> None:
        self.context = context
        self.deps = deps

    def register(self, router: APIRouter) -> None:
        auth_dependencies = [Depends(self.deps.require_auth)]

        router.add_api_route(
            "/api/status",
            self.get_status,
            methods=["GET"],
            dependencies=auth_dependencies,
            tags=["System"],
        )
        router.add_api_route(
            "/api/config/prefix",
            self.change_prefix,
            methods=["POST"],
            dependencies=auth_dependencies,
            tags=["System"],
        )
        router.add_api_route(
            "/api/config/host",
            self.change_host,
            methods=["POST"],
            dependencies=auth_dependencies,
            tags=["System"],
        )

    async def get_status(self):
        return await self.context.system_service.get_status()

    async def change_prefix(self, data: PrefixRequest):
        return await self.context.system_service.change_prefix(data.prefix)
    
    async def change_host(self, data: HostRequest):
        return await self.context.system_service.change_host(data.host)
        
