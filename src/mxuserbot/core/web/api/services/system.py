from typing import Any


class SystemService:
    def __init__(self, mx: Any) -> None:
        self.mx = mx

    async def is_authenticated(self) -> bool:
        return bool(await self.mx._db.get("core", "access_token"))


    async def get_status(self) -> dict[str, Any]:
        return {
            "status": "ONLINE",
            "modules_count": len(self.mx.active_modules),
            "version": getattr(self.mx, "version", "3.0.0"),
            "start_time": getattr(self.mx, "start_time", 0),
        }


    async def change_prefix(self, prefix: str) -> dict[str, str]:
        await self.mx._db.set("core", "prefix", [prefix])
        if hasattr(self.mx, "_prefixes"):
            self.mx._prefixes = [prefix]

        return {"status": "ok", "prefix": prefix}
