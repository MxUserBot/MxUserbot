from typing import Any

from fastapi import HTTPException

from ..schemas import InstallRequest, UninstallRequest


class ModuleService:
    def __init__(self, mx: Any) -> None:
        self.mx = mx


    async def get_module_config(
        self,
        module_id: str,
        repo: Any
    ) -> dict[str, Any]:
        result = await repo.get_module_config_schema(module_id)
        if not result.get("configurable"):
            raise HTTPException(
                status_code=404,
                detail="Module not configurable"
            )
        return result


    async def update_module_config(
        self,
        module_id: str,
        config: dict[str, Any]
    ) -> dict[str, str]:
        mod = self.mx.active_modules.get(module_id)
        meta = getattr(mod, "Meta", None) if mod else None
        if not mod or not meta or not getattr(meta, "has_config", False):
            raise HTTPException(
                status_code=404,
                detail="Module not configurable"
            )

        for key, value in config.items():
            cfg_val = mod.config._schema.get(key)
            if cfg_val and not self._is_config_editable(cfg_val):
                continue

            if not mod.config.set(key, value):
                raise HTTPException(
                    status_code=400,
                    detail=f"Validation failed for '{key}'"
                )

        return {"status": "ok"}


    async def get_installed_modules(
        self,
        repo: Any
    ) -> list[dict[str, Any]]:
        return await repo.get_installed()


    async def search_modules(
        self,
        query: str,
        repo: Any
    ) -> list[dict[str, Any]]:
        results = await repo.search(query.lower())
        formatted: list[dict[str, Any]] = []

        for repo_result in results:
            repo_url = repo_result["repo_url"]
            is_verified = repo_result["is_verified"]
            target_prefix = self._build_target_prefix(repo_url, is_verified)

            for module_meta in repo_result["modules"]:
                module_id = module_meta["id"]
                formatted.append(
                    {
                        "id": module_id,
                        "name": module_meta.get("name", module_id),
                        "description": module_meta.get("description") or "No description provided",
                        "version": module_meta.get("version", "0.0.1"),
                        "author": module_meta.get("author", "Unknown"),
                        "tags": module_meta.get("tags", []),
                        "repo_url": repo_url,
                        "is_verified": is_verified,
                        "target": f"{target_prefix}{module_id}",
                        "raw_url": module_meta.get("url"),
                        "is_installed": module_id in self.mx.active_modules,
                    }
                )

        return formatted


    async def install_module(
        self,
        req: InstallRequest,
        repo: Any
    ) -> dict[str, str]:
        try:
            if req.target.startswith("http") and not req.is_dev:
                raise HTTPException(
                    status_code=400,
                    detail="Direct links require 'is_dev': true"
                )

            if not await repo.install(req.target):
                raise HTTPException(
                    status_code=400,
                    detail="Loader rejected module structure or download failed",
                )

            return {
                "status": "ok",
                "target": req.target
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=str(exc)
            ) from exc


    async def uninstall_module(
        self,
        req: UninstallRequest,
        repo: Any
    ) -> dict[str, str]:
        if req.module_id not in self.mx.active_modules:
            raise HTTPException(
                status_code=404,
                detail="Module not active"
            )

        try:
            await repo.uninstall(req.module_id)
            return {
                "status": "ok",
                "module_id": req.module_id
            }
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=str(exc)
            ) from exc


    async def reload_modules(
        self
    ) -> dict[str, Any]:
        try:
            await self.mx.all_modules.register_all(self.mx.interface)
            return {
                "status": "ok",
                "count": len(self.mx.active_modules)
            }
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=str(exc)
            ) from exc


    def _is_config_editable(
        self,
        cfg_val: Any
    ) -> bool:
        if hasattr(cfg_val, "editable"):
            return bool(getattr(cfg_val, "editable"))
        return not bool(getattr(cfg_val, "forbid", False))


    def _build_target_prefix(
        self,
        repo_url: str,
        is_verified: bool
    ) -> str:
        if is_verified:
            return ""

        if "github" not in repo_url:
            return "comm/"

        parts = repo_url.rstrip("/").split("/")
        if len(parts) > 3:
            return f"{parts[3]}/"
        return "comm/"
