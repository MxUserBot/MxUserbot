# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import ast
import asyncio
import hashlib
import importlib.util
import inspect
import io
import json
import re
import shutil
import sys
import tempfile
import time
import types
import typing
import zipfile
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from mautrix.crypto.attachments import decrypt_attachment
from mautrix.types import EncryptedEvent, EventType, MessageType

from mxc import utils
from .security import ALL, EVERYONE, OWNER, SUDO, ScopedDatabase, COMM_MARKERS
from .module import ConfigValue, Module

_MODULE_NAME_BY_HASH: typing.Dict[str, str] = {}

ALL = ALL
SUDO = SUDO
OWNER = OWNER
EVERYONE = EVERYONE


def _is_community_in_stack(depth=10):
    for i in range(1, depth):
        try:
            f = sys._getframe(i)
            fn = f.f_code.co_filename.replace("\\", "/")
            if any(m in fn for m in COMM_MARKERS):
                return True
        except ValueError:
            break
    return False


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



def on(
    event_type: EventType
):
    def decorator(func):
        func.is_event_handler = True
        func.handled_event_type = event_type
        return func
    return decorator


def watcher(
    regex: str,
    security=EVERYONE
):
    def decorator(func):
        func.is_watcher = True
        func.regex = re.compile(regex, re.IGNORECASE)
        func.security = security
        return func
    return decorator


def command(
    name=None,
    aliases: list = None,
    security=SUDO
):
    def decorator(func):
        func.is_command = True
        func.command_name = (name or func.__name__).lower()
        func.aliases = [a.lower() for a in (aliases or [])]
        func.security = security
        return func
    return decorator


def state(target_state):
    def decorator(func):
        func.is_state = True
        func.target_state = target_state.state if hasattr(target_state, 'state') else target_state
        return func
    return decorator


def cron(expr_or_interval: str):
    def decorator(func):
        func.is_cron = True
        func.cron_interval = _parse_cron(expr_or_interval)
        return func
    return decorator


def _parse_cron(s: str) -> float:
    s = s.strip().lower()
    m = re.match(r'^(\d+)\s*([smh])$', s)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        if unit == 's': return float(val)
        if unit == 'm': return float(val * 60)
        if unit == 'h': return float(val * 3600)
    parts = s.split()
    if len(parts) >= 1 and re.match(r'^\*/\d+$', parts[0]):
        return float(int(parts[0][2:]) * 60)
    if len(parts) >= 2 and parts[0] == '0' and parts[1] == '*':
        return 3600.0
    return 60.0


def _calc_module_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest()


def tds(cls):
    if not hasattr(cls, 'strings'):
        cls.strings = {}

    @wraps(cls._internal_init)
    async def _internal_init(self, *args, **kwargs):
        def proccess_decorators(mark: str, obj: str):
            nonlocal self
            for attr in dir(func_):
                if (
                    attr.endswith("_doc")
                    and len(attr) == 6
                    and isinstance(getattr(func_, attr), str)
                ):
                    var = f"strings_{attr.split('_')[0]}"
                    if not hasattr(self, var):
                        setattr(self, var, {})

                    getattr(self, var).setdefault(f"{mark}{obj}", getattr(func_, attr))

        for command_, func_ in utils.get_commands(cls).items():
            proccess_decorators("_cmd_doc_", command_)
            try:
                func_.__doc__ = self.strings[f"_cmd_doc_{command_}"]
            except AttributeError:
                func_.__func__.__doc__ = self.strings[f"_cmd_doc_{command_}"]

        return await self._internal_init._old_(self, *args, **kwargs)

    _internal_init._old_ = cls._internal_init
    cls._internal_init = _internal_init

    for command_, func in utils.get_commands(cls).items():
        cmd_doc = func.__doc__
        if cmd_doc:
            cls.strings.setdefault(f"_cmd_doc_{command_}", inspect.cleandoc(cmd_doc))

    return cls


class Loader:
    def __init__(self, db_wrapper):
        self._db = db_wrapper
        self.active_modules: typing.Dict[str, object] = {}
        self.module_path = Path(__file__).resolve().parents[2] / 'mxuserbot'
        self.core_path = self.module_path / "modules"
        self.community_path = self.module_path / "community"

        self._background_tasks: typing.Set[asyncio.Task] = set()
        self.command_registry: typing.Dict[str, typing.Dict[str, typing.Any]] = {} 


    async def register_all(
        self,
        bot
    ) -> None:
        for p in [self.core_path, self.community_path]:
            p.mkdir(parents=True, exist_ok=True)

        await self._load_from_directory(
            self.core_path,
            bot, 
            is_core=True
        )

        await self._load_from_directory(
            self.community_path,
            bot,
            is_core=False
        )

        logger.info(f"Load modules: {len(self.active_modules)}.")


    async def _load_from_directory(
        self,
        path: Path,
        bot,
        is_core: bool
    ) -> None:
        coros = []
        for entry in path.iterdir():
            if entry.suffix == ".py" and not entry.name.startswith("_"):
                coros.append(self.register_module(entry, bot, is_core=is_core))
            elif entry.is_dir() and not entry.name.startswith("_") and (entry / "__init__.py").exists():
                coros.append(self.register_package(entry, bot, is_core=is_core))
        if coros:
            results = await asyncio.gather(*coros, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Module load error: {r}")


    async def show_module_help(self, mx, event, filename: str) -> None:
        async def _inner():
            mod_name = filename.replace(".py", "").replace(".zip", "")
            mod = self.active_modules.get(mod_name)
            if not mod:
                return

            prefix = await utils.get_prefix(mx)
            meta = getattr(mod, "Meta", None)
            name = getattr(meta, "name", mod_name)
            desc = getattr(meta, "description", "—")
            version = getattr(meta, "version", "")

            lines = [f"<b>📦 | {name}</b>"]
            if version:
                lines[0] += f" <i>v{version}</i>"
            lines.append(f"<b>ℹ️ | Description:</b> <i>{desc}</i><br>")

            if hasattr(mod, "config") and hasattr(mod.config, "_schema"):
                lines.append("<b>⚙️ | Configuration:</b><br>")
                for key, cfg_val in mod.config._schema.items():
                    lines.append(
                        f"    ⬥ <code>{key}</code>: "
                        f"<i>{cfg_val.description or '—'}</i> "
                        f"(Current: <code>{mod.config[key]}</code>)<br>"
                    )

            commands = getattr(mod, "commands", {})
            if commands:
                lines.append("<b>🛠 | Commands:</b><br>")
                for cmd_name, func in commands.items():
                    cmd_desc = (func.__doc__ or "—").replace("<", "&lt;").replace(">", "&gt;")
                    lines.append(f" • <code>{prefix}{cmd_name}</code> — <i>{cmd_desc}</i><br>")

            await utils.answer(mx, "".join(lines), event=event)

        try:
            await _inner()
        except Exception:
            pass


    async def register_module(
        self,
        path: Path,
        bot,
        is_core: bool = False
    ):
        subfolder = "core" if is_core else "community"
        module_name = f"src.mxuserbot.{subfolder}.{path.stem}"
        
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(path))
            if not spec or not spec.loader:
                return

            module = importlib.util.module_from_spec(spec)
            module.__package__ = f"src.mxuserbot.{subfolder}"

            try:
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            except Exception as e:
                logger.error(f"[{path.stem}] Execution error: {e}")
                sys.modules.pop(module_name, None)
                return

            if not hasattr(module, 'Meta'):
                logger.info(f"[{path.stem}] class Meta not found in module. Module not load.")
                return

            module_meta = module.Meta

            required_meta_vars = [
                "name",
                "description",
                "tags",
                "version"
            ]

            for req in required_meta_vars:
                val = getattr(module_meta, req, None)
                if not val or not str(val).strip():
                    logger.error(f"[{path.stem}] Meta class is missing the required '{req}' attribute or it is empty. Module startup failed.")
                    return

            cls = None
            for attr_name in dir(module):
                if "Module" in attr_name:
                    potential_cls = getattr(module, attr_name)
                    if inspect.isclass(potential_cls) and potential_cls.__module__ == module.__name__:
                        cls = potential_cls
                        break

            if not cls:
                logger.warning(f"[{path.stem}] Class named '*Module' not found. Module skipped.")
                return

            short_name = path.stem

            if not is_core:
                if short_name in self.active_modules:
                    return
                
                for loaded_mod in self.active_modules.values():
                    if loaded_mod.__class__.__name__ == cls.__name__:
                        logger.warning(f"[COMM] | class '{cls.__name__}' is used core-module")
                        return
                    if loaded_mod.Meta.name == module_meta.name:
                        logger.warning(f"[COMM] | class '{module_meta.name}' is used core-module")
                        return

            cls.Meta = module_meta

            self._install_secure_setattr(cls, is_core)
            instance = await self._init_instance(cls, module_meta, short_name, bot, is_core, spec)

            self.active_modules[short_name] = instance

            startup_task = asyncio.create_task(self._finalize_module_startup(instance, bot, short_name))
            self._background_tasks.add(startup_task)
            startup_task.add_done_callback(self._background_tasks.discard)

        except Exception:
            logger.exception(f"Error module import {path.name}")


    async def register_package(
        self,
        pkg_dir: Path,
        bot,
        is_core: bool = False
    ):
        subfolder = "core" if is_core else "community"
        pkg_name = f"src.mxuserbot.{subfolder}.{pkg_dir.name}"
        short_name = pkg_dir.name

        try:
            init_file = pkg_dir / "__init__.py"
            if not init_file.exists():
                return

            parent_name = f"src.mxuserbot.{subfolder}"
            if parent_name not in sys.modules:
                parent_mod = types.ModuleType(parent_name)
                parent_mod.__path__ = [str(getattr(self, f"{subfolder}_path"))]
                sys.modules[parent_name] = parent_mod

            init_spec = importlib.util.spec_from_file_location(pkg_name, str(init_file))
            if not init_spec or not init_spec.loader:
                return

            pkg_module = importlib.util.module_from_spec(init_spec)
            pkg_module.__package__ = pkg_name
            pkg_module.__path__ = [str(pkg_dir)]
            sys.modules[pkg_name] = pkg_module
            init_spec.loader.exec_module(pkg_module)

            all_py_files = [f for f in sorted(pkg_dir.rglob("*.py")) if f != init_file]
            for py_file in all_py_files:
                rel = py_file.relative_to(pkg_dir)
                sub_name = f"{pkg_name}.{rel.with_suffix('').as_posix().replace('/', '.')}"

                if sub_name in sys.modules:
                    continue

                sub_spec = importlib.util.spec_from_file_location(sub_name, str(py_file))
                if not sub_spec or not sub_spec.loader:
                    continue

                sub_mod = importlib.util.module_from_spec(sub_spec)
                sub_mod.__package__ = pkg_name
                sys.modules[sub_name] = sub_mod
                try:
                    sub_spec.loader.exec_module(sub_mod)
                except Exception as e:
                    logger.error(f"[{short_name}] Submodule '{sub_name}' execution error: {e}")
                    sys.modules.pop(sub_name, None)

            if not hasattr(pkg_module, 'Meta'):
                logger.info(f"[{short_name}] class Meta not found in package __init__.py. Package not load.")
                self._cleanup_package_modules(pkg_name)
                return

            module_meta = pkg_module.Meta

            required_meta_vars = ["name", "description", "tags", "version"]
            for req in required_meta_vars:
                val = getattr(module_meta, req, None)
                if not val or not str(val).strip():
                    logger.error(f"[{short_name}] Meta class is missing the required '{req}' attribute or it is empty. Package startup failed.")
                    self._cleanup_package_modules(pkg_name)
                    return

            cls = None
            cls_source_module = None
            for mod_name, mod in list(sys.modules.items()):
                if mod_name == pkg_name or mod_name.startswith(f"{pkg_name}."):
                    for attr_name in dir(mod):
                        if "Module" in attr_name:
                            potential_cls = getattr(mod, attr_name)
                            if inspect.isclass(potential_cls) and potential_cls.__module__ == mod_name:
                                cls = potential_cls
                                cls_source_module = mod
                                break
                    if cls:
                        break

            if not cls:
                logger.warning(f"[{short_name}] Class named '*Module' not found in package. Package skipped.")
                self._cleanup_package_modules(pkg_name)
                return

            if not is_core:
                if short_name in self.active_modules:
                    return

                for loaded_mod in self.active_modules.values():
                    if loaded_mod.__class__.__name__ == cls.__name__:
                        logger.warning(f"[{short_name}] class '{cls.__name__}' is already loaded")
                        return
                    if loaded_mod.Meta.name == module_meta.name:
                        logger.warning(f"[{short_name}] module '{module_meta.name}' is already loaded")
                        return

            cls.Meta = module_meta

            self._install_secure_setattr(cls, is_core)
            cls_spec = None
            if cls_source_module and hasattr(cls_source_module, '__spec__'):
                cls_spec = cls_source_module.__spec__
            instance = await self._init_instance(cls, module_meta, short_name, bot, is_core, cls_spec or init_spec)

            self.active_modules[short_name] = instance

            startup_task = asyncio.create_task(
                self._finalize_module_startup(
                    instance, 
                    bot, 
                    short_name
                )
            )

            self._background_tasks.add(startup_task)
            startup_task.add_done_callback(self._background_tasks.discard)

        except Exception:
            logger.exception(f"Error package import {pkg_dir.name}")
            self._cleanup_package_modules(pkg_name)


    def _install_secure_setattr(self, cls, is_core: bool):
        if is_core:
            def secure_setattr(obj, name, value):
                if _is_community_in_stack():
                    raise PermissionError("Core modules are frozen in memory and cannot be modified!")
                object.__setattr__(obj, name, value)
            cls.__setattr__ = secure_setattr


    async def _init_instance(self, cls, module_meta, short_name, bot, is_core, spec):
        instance = cls()
        instance._is_ready = False
        instance._is_core = is_core

        if hasattr(instance, '_internal_init'):
            if is_core:
                db_to_pass = self._db
                loader_to_pass = self
            else:
                db_to_pass = ScopedDatabase(self._db, short_name)
                loader_to_pass = self.active_modules

            await instance._internal_init(short_name, db_to_pass, loader_to_pass, is_core=is_core)

        if not is_core:
            has_cfg = False
            if hasattr(instance, "config") and hasattr(instance.config, "_schema"):
                if len(instance.config._schema) > 0:
                    has_cfg = True
            instance.Meta.has_config = has_cfg

        if hasattr(instance, "commands"):
            instance._event_handlers = {}
            instance._watchers = []

            for attr_name in dir(instance):
                attr = getattr(instance, attr_name)

                if getattr(attr, "is_event_handler", False):
                    etype = attr.handled_event_type
                    instance._event_handlers.setdefault(etype, []).append(attr)

                if getattr(attr, "is_watcher", False):
                    instance._watchers.append(attr)

            for cmd_name, func in instance.commands.items():
                self.command_registry[cmd_name] = {
                    "module": instance,
                    "func": func
                }
                for alias in getattr(func, "aliases", []):
                    self.command_registry[alias] = self.command_registry[cmd_name]

        instance._cron_tasks = []
        for attr_name in dir(instance):
            attr = getattr(instance, attr_name)
            if callable(attr) and getattr(attr, "is_cron", False):
                instance._cron_tasks.append(attr)

        self._apply_metadata(instance, spec)
        return instance


    def _cleanup_package_modules(
        self,
        pkg_name: str
    ) -> None:
        to_delete = [m for m in list(sys.modules) if m == pkg_name or m.startswith(f"{pkg_name}.")]
        for m in to_delete:
            sys.modules.pop(m, None)


    async def unload_module(
        self,
        name: str,
        bot
    ) -> bool:
        if name not in self.active_modules:
            return False

        instance = self.active_modules[name]

        for task in getattr(instance, "_cron_tasks", []):
            task.cancel()

        if hasattr(instance, "commands"):
            for cmd_name, func in instance.commands.items():
                self.command_registry.pop(cmd_name, None)
                for alias in getattr(func, "aliases", []):
                    self.command_registry.pop(alias, None)

        try:
            if hasattr(instance, "_matrix_stop"):
                passed_bot = bot if instance._is_core else bot.interface
                if inspect.iscoroutinefunction(instance._matrix_stop):
                    await instance._matrix_stop(passed_bot)
                else:
                    instance._matrix_stop(passed_bot)
        except Exception as e:
            raise e

        prefixes = [
            f"src.mxuserbot.community.{name}",
            f"src.mxuserbot.core.{name}",
        ]
        for mod_name in list(sys.modules):
            for p in prefixes:
                if mod_name == p or mod_name.startswith(f"{p}."):
                    del sys.modules[mod_name]
                    break

        del self.active_modules[name]
        logger.success(f"Module {name} success unloaded!")
        return True


    async def _finalize_module_startup(
        self,
        instance,
        bot,
        name
    ):
        try:
            if hasattr(instance, "set_settings"):
                saved_settings = await self._db.get(name, "__config__")
                if saved_settings:
                    instance.set_settings(saved_settings)

            passed_bot = bot if instance._is_core else bot.interface
            
            if getattr(instance, "enabled", True) and hasattr(instance, "_matrix_start"):
                await instance._matrix_start(passed_bot)

            instance._cron_tasks = [
                asyncio.create_task(self._cron_loop(passed_bot, func, instance))
                for func in getattr(instance, "_cron_tasks", [])
            ]

            instance._is_ready = True


            
            logger.success(f"Module {name} is started!")
        except Exception as e:
            raise e

    async def _cron_loop(self, mx, func, instance):
        try:
            interval = func.cron_interval
            while True:
                await asyncio.sleep(interval)
                await func(mx)
        except asyncio.CancelledError:
            pass

    def _apply_metadata(
        self,
        instance,
        spec
    ) -> None:
        try:
            with open(spec.origin, 'r', encoding='utf-8') as f:
                source = f.read()
            instance.__source__ = source
            instance.__module_hash__ = _calc_module_hash(source)
            instance.__origin__ = spec.origin
            _MODULE_NAME_BY_HASH[instance.__module_hash__] = instance.__class__.__name__
        except Exception:
            instance.__module_hash__ = "unknown"


class RepoManager:
    def __init__(self, mx, db, system_repo_url: str = "https://raw.githubusercontent.com/MxUserBot/mx-modules/main"):
        self.mx = mx
        self.loader = mx.all_modules
        self.sys_repo = system_repo_url.rstrip("/")
        self.db = db
        self._index_cache = {}
        self._cache_ttl = 300 #


    def __getattr__(self, name: str):
        if name in self.mx.active_modules:
            return self.mx.active_modules[name]
        raise AttributeError()


    async def get_repos(self) -> List[str]:
        raw = await self.db.get("core", "community_repos")
        if not raw: return []
        return raw if isinstance(raw, list) else json.loads(raw)
    
    async def resolve_module(
        self,
        target: str
    ) -> Optional[ModuleMeta]:
        community_repos = await self.get_repos()
        
        if target.startswith(("http://", "https://")) and (target.endswith(".py") or target.endswith(".zip")):
            return ModuleMeta(
                id=target.split("/")[-1].replace(".py", "").replace(".zip", ""),
                name="Direct Link",
                url=target,
                is_verified=False,
                filename=target.split("/")[-1]
            )

        all_repos = [
            (self.sys_repo, True)] + [(r, False) for r in community_repos
        ]
        
        prefix, _, mod_id = target.rpartition("/")
        
        for repo_url, is_verified in all_repos:
            if prefix and prefix.lower() not in repo_url.lower():
                continue
                
            modules = await self._fetch_index(repo_url)
            meta = next((m for m in modules if m.get("id") == (mod_id or target)), None)
            
            if meta:
                return ModuleMeta(
                    id=meta["id"],
                    name=meta.get("name", "Unknown"),
                    url=f"{repo_url.rstrip('/')}/{meta['path'].lstrip('/')}",
                    is_verified=is_verified,
                    filename=meta["path"].split("/")[-1]
                )
        return None
    

    async def _get_all_sources(self) -> List[RepoSource]:
        sources = [RepoSource(url=self.sys_repo, is_verified=True)]
        
        raw_repos = await self.db.get("core", "community_repos")
        if not raw_repos: 
            return sources
            
        try:
            repo_list = raw_repos if isinstance(raw_repos, list) else json.loads(raw_repos)
            for url in repo_list:
                if isinstance(url, str):
                    sources.append(RepoSource(url=url.rstrip("/"), is_verified=False))
        except Exception as e:
            raise e
                
        return sources

    async def _fetch_index(self, repo_url: str) -> Dict[str, Any]:
            now = time.time()
            repo_url = repo_url.rstrip('/')
            
            if repo_url in self._index_cache:
                data, ts = self._index_cache[repo_url]
                if now - ts < self._cache_ttl:
                    return data

            try:
                data = await utils.request(f"{repo_url}/index.json", return_type="json")
                
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
                logger.error(f"ОШИБКА ПРИ ЗАГРУЗКЕ ИЛИ ВАЛИДАЦИИ ИНДЕКСА {repo_url}: {e}")
                return {}

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
                if isinstance(tags, str): tags = [tags]
                
                tags_str = " ".join(tags)
                search_str = f"{mod_id} {m.get('name', '')} {m.get('description', '')} {tags_str}".lower()
                
                if not query or query in search_str:
                    mod_data = m.copy()
                    mod_data["id"] = mod_id
                    matches.append(mod_data)
            
            if not matches: return None
                
            return {
                "repo_url": source.url,
                "is_verified": source.is_verified,
                "modules": matches
            }

        results = await asyncio.gather(*(scan_repo(s) for s in sources))
        return [r for r in results if r]

    async def resolve_and_download(
        self,
        target: str
    ) -> tuple[Optional[str], Optional[RepoSource]]:
        sources = await self._get_all_sources()
        
        if target.startswith(("http://", "https://")) and (target.endswith(".py") or target.endswith(".zip")):
            return target, RepoSource(url=target, is_verified=False)

        prefix, _, mod_id = target.rpartition("/")
        search_id = (mod_id or target).lower()

        for source in sources:
            if prefix and prefix.lower() not in source.url.lower():
                continue
                
            index_data = await self._fetch_index(source.url)
            if not index_data: continue
            
            found_id = next((k for k in index_data.keys() if k.lower() == search_id), None)
            
            if found_id:
                full_url = index_data[found_id]["url"]
                return full_url, source
        
        return None, None


    async def _run_uv(self, action: str, packages: List[str]) -> bool:
        if not packages:
            return True
            
        cmd = ["uv", "add"] + packages
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                logger.error(f"❌ UV ERROR: {stderr.decode('utf-8')}")
                return False
                
            logger.success(f"✅ | dependencies installed success")
            return True
        except Exception as e:
            raise e


    async def _install_dependencies(
        self,
        module_id: str, 
        deps: List[str]
    ) -> bool:
        if not deps:
            return True
        
        state_str = await self.db.get("core", "dep_map")
        dep_map = json.loads(state_str) if state_str else {}
        
        to_install =[]
        for dep in deps:
            base_dep = re.split(r'[<>=!~]', dep)[0].strip().lower()
            
            if base_dep not in dep_map:
                dep_map[base_dep] = []
            
            if module_id not in dep_map[base_dep]:
                dep_map[base_dep].append(module_id)
            
            to_install.append(dep)
            
        if to_install:
            success = await self._run_uv("install", to_install)
            if not success:
                raise RuntimeError("error installed dependencies...")
                
        await self.db.set("core", "dep_map", json.dumps(dep_map))
        return True


    async def _remove_dependencies(
        self,
        module_id: str
    ) -> None:
        state_str = await self.db.get("core", "dep_map")
        if not state_str: return
        dep_map = json.loads(state_str)
        
        to_remove =[]
        for dep, modules in list(dep_map.items()):
            if module_id in modules:
                modules.remove(module_id)
                if not modules:
                    to_remove.append(dep)
                    del dep_map[dep]
                    
        if to_remove:
            await self._run_uv("uninstall", to_remove)
            
        await self.db.set("core", "dep_map", json.dumps(dep_map))


    async def install_code(
        self,
        code: str,
        filename: str
    ) -> bool:
        try:
            tree_node = ast.parse(code)
        except SyntaxError as se:
            raise ValueError(f"Syntax error in module code: {se.msg} (line {se.lineno})")

        meta_node = None
        for node in ast.walk(tree_node):
            if isinstance(node, ast.ClassDef) and node.name == "Meta":
                meta_node = node
                break

        if not meta_node:
            raise ValueError("Invalid module: 'class Meta' not found!")

        module_deps =[]
        for stmt in meta_node.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if getattr(t, 'id', '') == 'dependencies':
                        if isinstance(stmt.value, (ast.List, ast.Tuple)):
                            module_deps =[
                                elt.value for elt in stmt.value.elts 
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            ]

        if not filename.endswith(".py"): 
            filename += ".py"
        short_name = filename[:-3]
        
        if module_deps:
            logger.info(f"📦 | install {short_name} dependencies: {module_deps}....")
            await self._install_dependencies(
                short_name,
                module_deps
            )
        
        path = Path(self.loader.community_path) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")

        await self.loader.register_module(path, self.mx, is_core=False)
        
        if path.stem not in self.mx.active_modules:
            await self._remove_dependencies(short_name)
            path.unlink(missing_ok=True)
            raise ValueError("Module failed to start. Check bot logs.")

        return True


    async def _install_zip(
        self,
        zip_bytes: bytes,
        filename: str
    ) -> bool:
        temp_dir = Path(tempfile.mkdtemp())

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
            for entry in zf.infolist():
                dest = Path(temp_dir) / entry.filename
                dest.relative_to(temp_dir)
            zf.extractall(str(temp_dir))

            extracted_dirs = [d for d in temp_dir.iterdir() if d.is_dir()]
            if not extracted_dirs:
                raise ValueError("Zip must contain a root directory (the module name)")

            pkg_dir = extracted_dirs[0]
            init_file = pkg_dir / "__init__.py"
            if not init_file.exists():
                raise ValueError("Invalid zip module: '__init__.py' not found in the root directory")

            init_code = init_file.read_text(encoding="utf-8")
            tree_node = ast.parse(init_code)

            meta_node = None
            for node in ast.walk(tree_node):
                if isinstance(node, ast.ClassDef) and node.name == "Meta":
                    meta_node = node
                    break

            if not meta_node:
                raise ValueError("Invalid zip module: 'class Meta' not found in __init__.py!")

            module_deps = []
            for stmt in meta_node.body:
                if isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        if getattr(t, 'id', '') == 'dependencies':
                            if isinstance(stmt.value, (ast.List, ast.Tuple)):
                                module_deps = [
                                    elt.value for elt in stmt.value.elts
                                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                                ]

            target_dir = Path(self.loader.community_path) / pkg_dir.name
            if target_dir.exists():
                raise ValueError(f"Module '{pkg_dir.name}' already exists!")

            if module_deps:
                await self._install_dependencies(pkg_dir.name, module_deps)

            shutil.copytree(str(pkg_dir), str(target_dir))

            await self.loader.register_package(target_dir, self.mx, is_core=False)

            if target_dir.name not in self.mx.active_modules:
                await self._remove_dependencies(pkg_dir.name)
                shutil.rmtree(str(target_dir), ignore_errors=True)
                raise ValueError("Zip module failed to start. Check bot logs.")

            return True

        except zipfile.BadZipFile:
            raise ValueError("Invalid zip file!")
        finally:
            shutil.rmtree(str(temp_dir), ignore_errors=True)


    async def install(
            self, 
            target: Optional[str] = None, 
            code: Optional[str] = None, 
            filename: Optional[str] = None
        ) -> bool:
            if target:
                url, source = await self.resolve_and_download(target)
                if not url:
                    raise ValueError(f"Module '{target}' not found in any repository")

                logger.info(f"⬇️ | Downloading module: {url}")
                if url.endswith(".zip"):
                    raw = await utils.request(url, return_type="bytes")
                    filename = url.split("/")[-1]
                    return await self._install_zip(raw, filename)
                else:
                    code = await utils.request(url, return_type="text")
                    filename = url.split("/")[-1]

            if not code or not filename:
                raise ValueError("No target or code provided for installation!")

            if isinstance(code, bytes) and filename.endswith(".zip"):
                return await self._install_zip(code, filename)

            if isinstance(code, bytes):
                code = code.decode("utf-8", errors="ignore")

            return await self.install_code(code, filename)


    async def uninstall(
        self,
        name: str
    ) -> None:
        actual_name = next(
            (k for k in self.loader.active_modules.keys() if k.lower() == name.lower()), 
            None
        )

        if not actual_name:
            for item in self.loader.community_path.iterdir():
                if item.is_dir() and item.name.lower() == name.lower():
                    actual_name = item.name
                    break
                if item.is_file() and item.suffix == ".py" and item.stem.lower() == name.lower():
                    actual_name = item.stem
                    break

        if not actual_name:
            raise ValueError(f"Module '{name}' not found!")

        await self.loader.unload_module(actual_name, self.mx)

        py_path = Path(self.loader.community_path) / f"{actual_name}.py"
        if py_path.exists():
            py_path.unlink()

        pkg_path = Path(self.loader.community_path) / actual_name
        if pkg_path.is_dir():
            shutil.rmtree(str(pkg_path), ignore_errors=True)

        await self._remove_dependencies(actual_name)
        logger.success(f"Module {actual_name} unloaded")

    async def get_file_content(
        self,
        event: Any
    ) -> tuple[str, bytes]:
        if isinstance(event, EncryptedEvent):
            decrypted = await self.mx.client.crypto.decrypt_megolm_event(event)
            content = decrypted.content
        else:
            content = event.content

        if content.msgtype != MessageType.FILE:
            raise ValueError("Is not file!")

        if content.file:
            ciphertext = await self.mx.client.download_media(content.file.url)
            data = decrypt_attachment(
                ciphertext, content.file.key.key, 
                content.file.hashes.get("sha256"), content.file.iv
            )
        else:
            data = await self.mx.client.download_media(content.url)
            
        return content.body, data


    async def get_module_config_schema(
        self,
        module_id: str
    ) -> Dict[str, Any]:
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


    async def get_installed(
        self
    ) -> List[dict[str, Any]]:
        
        installed = []
        
        for m_id, mod in self.mx.active_modules.items():
            meta = getattr(
                mod, "Meta", None
            )
            is_core = getattr (
                mod, "_is_core", False
            )
            name = getattr(
                meta, "name", m_id
            )
            description = getattr(
                meta, "description", "no desc."
            )
            version = getattr(
                meta, "version", None
            )
            tags = getattr(
                meta, "tags", []
            )


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
        
        return sorted(
            installed,
            key=lambda x: (not x["is_core"], x["name"].lower())
        )