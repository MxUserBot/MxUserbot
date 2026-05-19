
# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import io
import ast
import json
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from mxc import utils
from mxc.types import DownloadMeta, EmojiButton
from mxc.utils.keyboard import EmojiKeyBoard

from .utils import _check_community_source, _parse_deps_from_code
from ..langs import STRINGS


@dataclass
class RepoSource:
    url: str
    is_verified: bool


@dataclass
class ModuleMeta:
    id: str
    name: str
    url: str
    is_verified: bool
    filename: str


class RepoManager:
    def __init__(self, mx, db, system_repo_url: str = "https://raw.githubusercontent.com/MxUserBot/mx-modules/main"):
        self.mx = mx
        self.strings = STRINGS
        self.loader = mx.all_modules
        self.sys_repo = system_repo_url.rstrip("/")
        self.db = db
        self._index_cache = {}
        self._cache_ttl = 300

    def __getattr__(self, name: str):
        if name in self.mx.active_modules:
            return self.mx.active_modules[name]
        raise AttributeError()

    async def get_repos(self) -> List[str]:
        raw = await self.db.get("LoaderModule", "community_repos")
        if not raw:
            return []
        return raw if isinstance(raw, list) else json.loads(raw)

    async def resolve_module(self, target: str) -> Optional[ModuleMeta]:
        sources = await self._get_all_sources()
        if target.startswith(("http://", "https://")) and (target.endswith(".py") or target.endswith(".zip")):
            return ModuleMeta(
                id=target.split("/")[-1].replace(".py", "").replace(".zip", ""),
                name="Direct Link",
                url=target,
                is_verified=False,
                filename=target.split("/")[-1]
            )
        prefix, _, mod_id = target.rpartition("/")
        search_id = (mod_id or target).lower()
        for source in sources:
            if prefix and prefix.lower() not in source.url.lower():
                continue
            index_data = await self._fetch_index(source.url)
            if not index_data:
                continue
            found_id = next((k for k in index_data.keys() if k.lower() == search_id), None)
            if found_id:
                m = index_data[found_id]
                url = m.get("url") or f"{source.url.rstrip('/')}/{m.get('path', '').lstrip('/')}"
                return ModuleMeta(
                    id=found_id,
                    name=m.get("name", "Unknown"),
                    url=url,
                    is_verified=source.is_verified,
                    filename=url.split("/")[-1]
                )
        return None

    async def resolve_and_download(self, target: str) -> tuple[Optional[str], Optional[RepoSource]]:
        meta = await self.resolve_module(target)
        if not meta:
            return None, None
        return meta.url, RepoSource(url=meta.url, is_verified=meta.is_verified)

    async def _get_all_sources(self) -> List[RepoSource]:
        sources = [RepoSource(url=self.sys_repo, is_verified=True)]
        for url in await self.get_repos():
            if isinstance(url, str):
                sources.append(RepoSource(url=url.rstrip("/"), is_verified=False))
        return sources

    async def _fetch_index(self, repo_url: str) -> Dict[str, Any]:
        now = time.time()
        repo_url = repo_url.rstrip('/')
        if repo_url in self._index_cache:
            data, ts = self._index_cache[repo_url]
            if now - ts < self._cache_ttl:
                return data
        try:
            cache_buster = f"?_={int(now)}"
            data = await asyncio.wait_for(
                utils.request(f"{repo_url}/index.json{cache_buster}", return_type="json"),
                timeout=15,
            )
            if not isinstance(data, dict):
                return {}
            for mod_id, meta in data.items():
                if not isinstance(meta, dict):
                    return {}
                required_fields = ["url", "name", "version"]
                if not all(field in meta for field in required_fields):
                    return {}
            self._index_cache[repo_url] = (data, now)
            return data
        except Exception as e:
            logger.error(f"Index fetch error {repo_url}: {e}")
            return {}

    async def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        sources = await self._get_all_sources()
        repo_indexes = {}
        for source in sources:
            idx = await self._fetch_index(source.url)
            if idx:
                repo_indexes[source.url] = {"index": idx, "is_verified": source.is_verified}

        for mod_id, mod in self.loader.active_modules.items():
            if getattr(mod, "_is_core", False):
                continue
            meta = getattr(mod, "Meta", None)
            if not meta:
                continue
            installed_version = getattr(meta, "version", None)
            if not installed_version:
                continue
            installed_version = str(installed_version).lstrip("v")
            mod_name = getattr(meta, "name", mod_id)

            for repo_url, repo_data in repo_indexes.items():
                idx = repo_data["index"]
                repo_entry = idx.get(mod_id) or next(
                    (v for k, v in idx.items() if v.get("name", "").lower() == mod_name.lower()),
                    None,
                )
                if not repo_entry:
                    continue
                repo_version = str(repo_entry.get("version", "")).lstrip("v")
                if not repo_version:
                    continue
                try:
                    iv = tuple(int(x) for x in installed_version.split("."))
                    rv = tuple(int(x) for x in repo_version.split("."))
                    if rv > iv:
                        updates.append({
                            "module_id": mod_id,
                            "name": mod_name,
                            "current": installed_version,
                            "available": repo_version,
                            "repo_url": repo_url,
                            "is_verified": repo_data["is_verified"],
                        })
                except (ValueError, TypeError):
                    if repo_version != installed_version:
                        updates.append({
                            "module_id": mod_id,
                            "name": mod_name,
                            "current": installed_version,
                            "available": repo_version,
                            "repo_url": repo_url,
                            "is_verified": repo_data["is_verified"],
                        })
                    continue
                break

        return sorted(updates, key=lambda x: x["name"].lower())

    async def search(self, query: str = "") -> List[Dict]:
        sources = await self._get_all_sources()
        query = query.lower().strip()
        async def scan_repo(source):
            index_data = await self._fetch_index(source.url)
            if not index_data or not isinstance(index_data, dict):
                return None
            matches = []
            for mod_id, m in index_data.items():
                if not isinstance(m, dict):
                    continue
                tags = m.get("tags", [])
                if isinstance(tags, str):
                    tags = [tags]
                tags_str = " ".join(tags)
                search_str = f"{mod_id} {m.get('name', '')} {m.get('description', '')} {tags_str}".lower()
                if not query or query in search_str:
                    mod_data = m.copy()
                    mod_data["id"] = mod_id
                    matches.append(mod_data)
            if not matches:
                return None
            return {"repo_url": source.url, "is_verified": source.is_verified, "modules": matches}
        results = await asyncio.gather(*(scan_repo(s) for s in sources))
        return [r for r in results if r]

    async def _run_uv(self, action: str, packages: List[str]) -> bool:
        if not packages:
            return True
        cmd = ["uv", "add"] + packages
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                err_msg = stderr.decode('utf-8').strip()
                logger.error(f"UV ERROR: {err_msg}")
                raise RuntimeError(self.strings.get("loader.dep_install_failed").format(err=err_msg))
            logger.success("dependencies installed success")
            return True
        except Exception as e:
            raise e

    async def check_dep_conflicts(self, deps: List[str], module_id: str) -> List[str]:
        state_str = await self.db.get("core", "dep_map")
        dep_map = json.loads(state_str) if state_str else {}
        conflicts = []
        for dep in deps:
            base = re.split(r'[<>=!~]', dep)[0].strip().lower()
            owners = dep_map.get(base, [])
            active = [o for o in owners if o != module_id and o in self.loader.active_modules]
            if active:
                conflicts.append(f"{dep} (used by: {', '.join(active)})")
        return conflicts

    async def _dep_conflict_poll(self, mx, event, module_id: str, conflicts: List[str]) -> bool:
        confirmed = asyncio.Event()
        result = [False]
        async def callback(ctx):
            if ctx.payload == "yes":
                result[0] = True
            confirmed.set()
        markup = EmojiKeyBoard(
            rows=[[
                EmojiButton(self.strings.get("loader.dep_confirm_yes"), "yes"),
                EmojiButton(self.strings.get("loader.dep_confirm_no"), "no"),
            ]],
            callback=callback,
        )
        conflict_lines = "<br>".join(f"  ⚠️ <code>{c}</code>" for c in conflicts)
        await utils.answer(mx, self.strings.get("loader.dep_conflict").format(id=module_id, conflicts=conflict_lines), event=event, reply_markup=markup)
        try:
            await asyncio.wait_for(confirmed.wait(), timeout=60)
        except asyncio.TimeoutError:
            return False
        return result[0]

    async def _install_dependencies(self, module_id: str, deps: List[str], event=None) -> bool:
        if not deps:
            return True
        state_str = await self.db.get("core", "dep_map")
        dep_map = json.loads(state_str) if state_str else {}
        if event:
            conflicts = await self.check_dep_conflicts(deps, module_id)
            if conflicts:
                ok = await self._dep_conflict_poll(self.mx, event, module_id, conflicts)
                if not ok:
                    raise RuntimeError(self.strings.get("loader.dep_conflict_cancelled"))
        to_install = []
        added = {}
        for dep in deps:
            base_dep = re.split(r'[<>=!~]', dep)[0].strip().lower()
            if base_dep not in dep_map:
                dep_map[base_dep] = []
            if module_id not in dep_map[base_dep]:
                dep_map[base_dep].append(module_id)
                added[base_dep] = True
            to_install.append(dep)
        if to_install:
            try:
                await self._run_uv("install", to_install)
            except Exception:
                for base_dep in added:
                    dep_map[base_dep] = [m for m in dep_map[base_dep] if m != module_id]
                    if not dep_map[base_dep]:
                        del dep_map[base_dep]
                await self.db.set("core", "dep_map", json.dumps(dep_map))
                raise
        await self.db.set("core", "dep_map", json.dumps(dep_map))
        return True

    async def _remove_dependencies(self, module_id: str) -> None:
        state_str = await self.db.get("core", "dep_map")
        if not state_str:
            return
        dep_map = json.loads(state_str)
        to_remove = []
        for dep, modules in list(dep_map.items()):
            if module_id in modules:
                modules.remove(module_id)
                if not modules:
                    to_remove.append(dep)
                    del dep_map[dep]
        if to_remove:
            await self._run_uv("uninstall", to_remove)
        await self.db.set("core", "dep_map", json.dumps(dep_map))

    async def install_code(self, code: str, filename: str, event=None) -> bool:
        try:
            ast.parse(code)
        except SyntaxError as se:
            raise ValueError(self.strings.get("loader.syntax_error").format(msg=se.msg, line=se.lineno))
        module_deps, has_meta = _parse_deps_from_code(code)
        if not has_meta:
            raise ValueError(self.strings.get("loader.no_meta"))
        if not filename.endswith(".py"):
            filename += ".py"
        short_name = filename[:-3]
        _check_community_source(code, short_name)
        if module_deps:
            logger.info(f"install {short_name} dependencies: {module_deps}....")
            try:
                await self._install_dependencies(short_name, module_deps, event=event)
            except Exception as e:
                raise RuntimeError(self.strings.get("loader.install_error_dep").format(name=short_name, err=e))
        path = Path(self.loader.community_path) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")
        await self.loader.register_module(path, self.mx, is_core=False)
        if path.stem not in self.mx.active_modules:
            await self._remove_dependencies(short_name)
            path.unlink(missing_ok=True)
            raise ValueError(self.strings.get("loader.module_failed").format(name=short_name))
        return True

    async def _install_zip(self, zip_bytes: bytes, filename: str, event=None) -> bool:
        temp_dir = Path(tempfile.mkdtemp())
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
            for entry in zf.infolist():
                dest = Path(temp_dir) / entry.filename
                dest.relative_to(temp_dir)
            zf.extractall(str(temp_dir))
            extracted_dirs = [d for d in temp_dir.iterdir() if d.is_dir()]
            if not extracted_dirs:
                raise ValueError(self.strings.get("loader.zip_no_root"))
            pkg_dir = extracted_dirs[0]
            init_file = pkg_dir / "__init__.py"
            if not init_file.exists():
                raise ValueError(self.strings.get("loader.zip_no_init"))
            init_code = init_file.read_text(encoding="utf-8")
            module_deps, _ = _parse_deps_from_code(init_code)
            target_dir = Path(self.loader.community_path) / pkg_dir.name
            if target_dir.exists():
                raise ValueError(self.strings.get("loader.module_exists").format(name=pkg_dir.name))
            if module_deps:
                try:
                    await self._install_dependencies(pkg_dir.name, module_deps, event=event)
                except Exception as e:
                    raise RuntimeError(self.strings.get("loader.install_error_dep").format(name=pkg_dir.name, err=e))
            shutil.copytree(str(pkg_dir), str(target_dir))
            await self.loader.register_package(target_dir, self.mx, is_core=False)
            if target_dir.name not in self.mx.active_modules:
                await self._remove_dependencies(pkg_dir.name)
                shutil.rmtree(str(target_dir), ignore_errors=True)
                raise ValueError(self.strings.get("loader.module_failed").format(name=pkg_dir.name))
            return True
        except zipfile.BadZipFile:
            raise ValueError(self.strings.get("loader.invalid_zip"))
        finally:
            try:
                shutil.rmtree(str(temp_dir))
            except Exception as e:
                logger.warning(f"Failed to clean up temp dir {temp_dir}: {e}")

    async def install(self, target: Optional[str] = None, code: Optional[str] = None, filename: Optional[str] = None, event=None) -> bool:
        if target:
            url, source = await self.resolve_and_download(target)
            if not url:
                raise ValueError(self.strings.get("loader.not_in_repo").format(target=target))
            logger.info(f"Downloading module: {url}")
            if url.endswith(".zip"):
                raw = await utils.request(url, return_type="bytes")
                filename = url.split("/")[-1]
                return await self._install_zip(raw, filename, event=event)
            else:
                code = await utils.request(url, return_type="text")
                filename = url.split("/")[-1]
        if not code or not filename:
            raise ValueError(self.strings.get("loader.no_target"))
        if isinstance(code, bytes) and filename.endswith(".zip"):
            return await self._install_zip(code, filename, event=event)
        if isinstance(code, bytes):
            code = code.decode("utf-8", errors="ignore")
        return await self.install_code(code, filename, event=event)

    async def uninstall(self, name: str) -> str:
        actual_name = next(
            (k for k in self.loader.active_modules.keys() if k.lower() == name.lower()),
            None
        )
        if not actual_name:
            for mod_id, mod in self.loader.active_modules.items():
                cls_name = mod.__class__.__name__.lower()
                meta_name = getattr(getattr(mod, "Meta", None), "name", "").lower()
                search = name.lower()
                if cls_name == search or cls_name.rstrip("module") == search:
                    actual_name = mod_id
                    break
                if meta_name == search:
                    actual_name = mod_id
                    break
        if not actual_name:
            for item in self.loader.community_path.iterdir():
                if item.is_dir() and item.name.lower() == name.lower():
                    actual_name = item.name
                    break
                if item.is_file() and item.suffix == ".py" and item.stem.lower() == name.lower():
                    actual_name = item.stem
                    break
        if not actual_name:
            raise ValueError(self.strings.get("loader.module_not_found").format(name=name))
        instance = self.loader.active_modules.get(actual_name)
        if instance and getattr(instance, "_is_core", False):
            raise ValueError(STRINGS("loader.core_frozen"))
        await self.loader.unload_module(actual_name, self.mx)
        py_path = Path(self.loader.community_path) / f"{actual_name}.py"
        if py_path.exists():
            py_path.unlink()
        pkg_path = Path(self.loader.community_path) / actual_name
        if pkg_path.is_dir():
            shutil.rmtree(str(pkg_path), ignore_errors=True)
        await self._remove_dependencies(actual_name)
        logger.success(f"Module {actual_name} unloaded")
        return actual_name

    async def get_file_content(self, event: Any) -> tuple[str, bytes]:
        data, filename, *_ = await utils.download(self.mx, DownloadMeta(url=event))
        return filename, data

    async def get_module_config_schema(self, module_id: str) -> Dict[str, Any]:
        mod = self.mx.active_modules.get(module_id)
        if not mod or not getattr(mod.Meta, "has_config", False):
            return {"configurable": False, "config": []}
        schema_info = []
        for key, cfg_val in mod.config._schema.items():
            is_forbidden = getattr(cfg_val, "forbid", False)
            schema_info.append({
                "key": key,
                "description": getattr(cfg_val, "description", ""),
                "value": mod.config.get(key),
                "required": getattr(cfg_val, "required", False),
                "editable": not is_forbidden
            })
        return {"configurable": True, "config": schema_info}

    async def get_installed(self) -> List[dict[str, Any]]:
        installed = []
        for m_id, mod in self.mx.active_modules.items():
            meta = getattr(mod, "Meta", None)
            is_core = getattr(mod, "_is_core", False)
            name = getattr(meta, "name", m_id)
            description = getattr(meta, "description", "no desc.")
            version = getattr(meta, "version", None)
            tags = getattr(meta, "tags", [])
            has_config = False
            if not is_core and hasattr(mod, "config") and hasattr(mod.config, "_schema"):
                schema = mod.config._schema
                if any(not getattr(val, "forbid", False) for val in schema.values()):
                    has_config = True
            installed.append({
                "id": m_id,
                "name": name,
                "description": description,
                "version": version,
                "tags": tags,
                "is_core": is_core,
                "is_installed": True,
                "has_config": has_config,
            })
        return sorted(installed, key=lambda x: (not x["is_core"], x["name"].lower()))
