# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..context import APIContext
from ..dependencies import APIDependencies
from ..schemas import LoginSchema, SSOInitSchema


class AuthController:
    def __init__(self, context: APIContext, deps: APIDependencies | None = None) -> None:
        self.context = context
        self.deps = deps

    def register(self, router: APIRouter) -> None:
        router.add_api_route(
            "/api/auth",
            self.api_auth,
            methods=["POST"],
            tags=["Auth"],
        )
        router.add_api_route(
            "/api/auth/sso/init",
            self.sso_init,
            methods=["POST"],
            tags=["Auth"],
        )
        router.add_api_route(
            "/api/auth/sso/callback",
            self.sso_callback,
            methods=["GET"],
            tags=["Auth"],
        )
        if self.deps:
            router.add_api_route(
                "/api/auth/logout",
                self.api_logout,
                methods=["POST"],
                dependencies=[Depends(self.deps.require_auth)],
                tags=["Auth"],
            )

    async def api_auth(self, data: LoginSchema):
        try:
            await self.context.auth_service.login(data, self.context.mx, self.context.auth_event)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {"status": "ok", "message": "Authenticated"}

    async def sso_init(self, data: SSOInitSchema):
        try:
            return await self.context.auth_service.init_sso(data.mxid, data.callback_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def sso_callback(self, request: Request):
        state = request.query_params.get("state")
        login_token = request.query_params.get("loginToken")

        if not state or not login_token:
            return RedirectResponse(url="/?error=missing_sso_params")

        try:
            await self.context.auth_service.complete_sso(
                state, login_token, self.context.mx, self.context.auth_event,
            )
            return RedirectResponse(url="/panel")
        except ValueError as exc:
            return RedirectResponse(url=f"/?error={exc}")

    async def api_logout(self):
        mx = self.context.mx
        for key in ("access_token", "username", "device_id", "base_url", "owner"):
            await mx._db.delete("core", key)
        mx.config.save()
        return {"status": "ok"}
