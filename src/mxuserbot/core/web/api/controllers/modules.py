from fastapi import APIRouter, Depends

from ..context import APIContext
from ..dependencies import APIDependencies
from ..schemas import ConfigUpdateRequest, InstallRequest, UninstallRequest


class ModuleController:
    def __init__(self, context: APIContext, deps: APIDependencies) -> None:
        self.context = context
        self.deps = deps

    def register(self, router: APIRouter) -> None:
        auth_dependencies = [Depends(self.deps.require_auth)]

        router.add_api_route(
            "/api/modules/{module_id}/config",
            self.get_module_config,
            methods=["GET"],
            dependencies=auth_dependencies,
            tags=["Config"],
        )
        router.add_api_route(
            "/api/modules/{module_id}/config",
            self.update_module_config,
            methods=["POST"],
            dependencies=auth_dependencies,
            tags=["Config"],
        )
        router.add_api_route(
            "/api/modules/installed",
            self.get_installed_modules,
            methods=["GET"],
            dependencies=auth_dependencies,
            tags=["Modules"],
        )
        router.add_api_route(
            "/api/modules/search",
            self.search_modules,
            methods=["GET"],
            dependencies=auth_dependencies,
            tags=["Modules"],
        )
        router.add_api_route(
            "/api/modules/install",
            self.install_module,
            methods=["POST"],
            dependencies=auth_dependencies,
            tags=["Modules"],
        )
        router.add_api_route(
            "/api/modules/uninstall",
            self.uninstall_module,
            methods=["POST"],
            dependencies=auth_dependencies,
            tags=["Modules"],
        )
        router.add_api_route(
            "/api/modules/reload",
            self.reload_modules,
            methods=["POST"],
            dependencies=auth_dependencies,
            tags=["Modules"],
        )

    async def get_module_config(self, module_id: str):
        repo = self.deps.get_repo_manager()
        return await self.context.module_service.get_module_config(module_id, repo)

    async def update_module_config(self, module_id: str, req: ConfigUpdateRequest):
        return await self.context.module_service.update_module_config(module_id, req.config)

    async def get_installed_modules(self):
        repo = self.deps.get_repo_manager()
        return await self.context.module_service.get_installed_modules(repo)

    async def search_modules(self, query: str = ""):
        repo = self.deps.get_repo_manager()
        return await self.context.module_service.search_modules(query, repo)

    async def install_module(self, req: InstallRequest):
        repo = self.deps.get_repo_manager()
        return await self.context.module_service.install_module(req, repo)

    async def uninstall_module(self, req: UninstallRequest):
        repo = self.deps.get_repo_manager()
        return await self.context.module_service.uninstall_module(req, repo)

    async def reload_modules(self):
        return await self.context.module_service.reload_modules()
