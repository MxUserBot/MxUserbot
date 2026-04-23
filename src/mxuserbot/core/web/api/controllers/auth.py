from fastapi import APIRouter, HTTPException

from ..context import APIContext
from ..schemas import LoginSchema


class AuthController:
    def __init__(self, context: APIContext) -> None:
        self.context = context

    def register(self, router: APIRouter) -> None:
        router.add_api_route(
            "/api/auth",
            self.api_auth,
            methods=["POST"],
            tags=["Auth"],
        )

    async def api_auth(self, data: LoginSchema):
        try:
            await self.context.auth_service.login(data, self.context.mx, self.context.auth_event)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {"status": "ok", "message": "Authenticated"}
