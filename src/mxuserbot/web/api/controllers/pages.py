# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..context import APIContext


class PageController:
    def __init__(self, context: APIContext) -> None:
        self.context = context

    def register(self, router: APIRouter) -> None:
        router.add_api_route(
            "/",
            self.get_login_page,
            methods=["GET"],
            response_class=HTMLResponse,
            tags=["Pages"],
        )
        router.add_api_route(
            "/panel",
            self.get_panel_page,
            methods=["GET"],
            response_class=HTMLResponse,
            tags=["Pages"],
        )
        router.add_api_route(
            "/api/locale",
            self.get_locale,
            methods=["GET"],
            tags=["System"],
        )

    async def get_login_page(self, request: Request):
        if await self.context.system_service.is_authenticated():
            return RedirectResponse(url="/panel")

        return self.context.templates.TemplateResponse(request=request, name="index.html")

    async def get_panel_page(self, request: Request):
        if not await self.context.system_service.is_authenticated():
            return RedirectResponse(url="/")

        return self.context.templates.TemplateResponse(request=request, name="panel.html")

    async def get_locale(self):
        return self.context.locale_service.get_locale_data()
