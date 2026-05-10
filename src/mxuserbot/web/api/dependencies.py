# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import logging
from typing import Any

from fastapi import HTTPException, Request
from loguru import logger


class APIDependencies:
    def __init__(self, mx: Any) -> None:
        self.mx = mx


    async def require_auth(self, request: Request) -> str:
        token = await self.mx._db.get("core", "access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return token


    def get_repo_manager(self) -> Any:
        loader_mod = self.mx.active_modules.get("loader")
        if not loader_mod or not hasattr(loader_mod, "repo"):
            logger.error("RepoManager is unavailable")
            raise HTTPException(status_code=500, detail="RepoManager is dead or missing!")
        return loader_mod.repo
