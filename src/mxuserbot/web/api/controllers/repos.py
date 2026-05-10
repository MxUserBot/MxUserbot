# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from fastapi import APIRouter, Depends

from ..context import APIContext
from ..dependencies import APIDependencies
from ..schemas import RepoActionRequest


class RepoController:
    def __init__(self, context: APIContext, deps: APIDependencies) -> None:
        self.context = context
        self.deps = deps

    def register(self, router: APIRouter) -> None:
        auth_dependencies = [Depends(self.deps.require_auth)]

        router.add_api_route(
            "/api/repos",
            self.get_repos,
            methods=["GET"],
            dependencies=auth_dependencies,
            tags=["Repos"],
        )
        router.add_api_route(
            "/api/repos/add",
            self.add_repo,
            methods=["POST"],
            dependencies=auth_dependencies,
            tags=["Repos"],
        )
        router.add_api_route(
            "/api/repos/remove",
            self.remove_repo,
            methods=["POST"],
            dependencies=auth_dependencies,
            tags=["Repos"],
        )

    async def get_repos(self):
        repo = self.deps.get_repo_manager()
        return await self.context.repo_service.get_repos(repo)

    async def add_repo(self, req: RepoActionRequest):
        repo = self.deps.get_repo_manager()
        return await self.context.repo_service.add_repo(req, repo)

    async def remove_repo(self, req: RepoActionRequest):
        repo = self.deps.get_repo_manager()
        return await self.context.repo_service.remove_repo(req, repo)
