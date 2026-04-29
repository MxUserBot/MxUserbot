import asyncio
import hashlib
import importlib.util
import inspect
import json
import re
import sys
import time
import typing
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from mautrix.crypto.attachments import decrypt_attachment
from mautrix.types import EncryptedEvent, EventType, MessageType

from . import utils
from .security import EVERYONE, OWNER, SUDO, ScopedDatabase
from .types import ConfigValue, Module  # для удобства импорта

_MODULE_NAME_BY_HASH: typing.Dict[str, str] = {}

SUDO = SUDO
OWNER = OWNER
EVERYONE = EVERYONE


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
        self.module_path = Path(__file__).resolve().parents[2] / 'mxuserbot' / 'modules'
        self.core_path = self.module_path / "core"
        self.community_path = self.module_path / "community"

        self._background_tasks: typing.Set[asyncio.Task] = set()
        self.command_registry: typing.Dict[str, typing.Dict[str, typing.Any]] = {} 


    async def register_all(
        self,
        bot
    ) -> None:
        for p in [self.core_path, self.community_path]:
            p.mkdir(parents=True, exist_ok=True)

        community_files = [f for f in self.community_path.iterdir() if f.suffix == ".py" and not f.name.startswith("_")]
        core_files = [f for f in self.core_path.iterdir() if f.suffix == ".py" and not f.name.startswith("_")]

        for path in core_files:
            await self.register_module(path, bot, is_core=True)

        for path in community_files:
            await self.register_module(path, bot, is_core=False)

        logger.info(f"Load modules: {len(self.active_modules)}.")


    async def register_module(
        self,
        path: Path,
        bot,
        is_core: bool = False
    ):
        subfolder = "core" if is_core else "community"
        module_name = f"src.mxuserbot.modules.{subfolder}.{path.stem}"
        
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(path))
            if not spec or not spec.loader:
                return

            module = importlib.util.module_from_spec(spec)
            module.__package__ = f"src.mxuserbot.modules.{subfolder}"

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

            required_meta_vars = ["name", "description", "tags", "version"]
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

            if is_core:
                def secure_setattr(obj, name, value):
                    for frame_info in inspect.stack():
                        if "modules/community" in frame_info.filename.replace("\\", "/"):
                            raise PermissionError(" Core modules are frozen in memory and cannot be modified!")
                    object.__setattr__(obj, name, value)
                
                cls.__setattr__ = secure_setattr
            
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
                instance._event_handlers = {} # {EventType: [funcs]}
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

            self._apply_metadata(instance, spec)
            
            self.active_modules[short_name] = instance

            startup_task = asyncio.create_task(self._finalize_module_startup(instance, bot, short_name))
            self._background_tasks.add(startup_task)
            startup_task.add_done_callback(self._background_tasks.discard)

        except Exception:
            logger.exception(f"Error module import {path.name}")


    async def unload_module(
        self,
        name: str,
        bot
    ) -> bool:
        if name not in self.active_modules:
            return False

        instance = self.active_modules[name]

        if hasattr(instance, "commands"):
            for cmd_name in instance.commands.keys():
                self.command_registry.pop(cmd_name, None)

        try:
            if hasattr(instance, "_matrix_stop"):
                if inspect.iscoroutinefunction(instance._matrix_stop):
                    await instance._matrix_stop(bot)
                else:
                    instance._matrix_stop(bot)
        except Exception as e:
            raise e

        module_name_to_del = None
        for mod_name in list(sys.modules.keys()):
            if mod_name.endswith(f".{name}") and "src.userbot.modules" in mod_name:
                module_name_to_del = mod_name
                break
        
        if module_name_to_del:
            del sys.modules[module_name_to_del]

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

            if getattr(instance, "enabled", True) and hasattr(instance, "_matrix_start"):
                await instance._matrix_start(bot)
            
            instance._is_ready = True


            
            logger.success(f"Module {name} is started!")
        except Exception as e:
            raise e

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
        self.loader = mx._bot.all_modules
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
        
        if target.startswith(("http://", "https://")) and target.endswith(".py"):
            return ModuleMeta(
                id=target.split("/")[-1].replace(".py", ""),
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

    async def resolve_and_download(self, target: str) -> tuple[Optional[str], Optional[RepoSource]]:
        sources = await self._get_all_sources()
        
        if target.startswith(("http://", "https://")) and target.endswith(".py"):
            return target, RepoSource(url=target, is_verified=False)

        prefix, _, mod_id = target.rpartition("/")
        search_id = mod_id or target

        for source in sources:
            if prefix and prefix.lower() not in source.url.lower():
                continue
                
            index_data = await self._fetch_index(source.url)
            if not index_data: continue
            
            if search_id in index_data:
                full_url = index_data[search_id]["url"]
                return full_url, source
        
        return None, None

    async def install(self, target: str) -> bool:
            import ast

            import aiohttp
            
            url, source = await self.resolve_and_download(target)
            if not url:
                raise ValueError(f"Module '{target}' not found in any repository")

            try:
                logger.info(f"⬇️ Downloading module: {url}")
                
                code = await utils.request(url, return_type="text")
                
                try:
                    tree_node = ast.parse(code)
                except SyntaxError as se:
                    raise ValueError(f"Syntax error in module code: {se.msg} (line {se.lineno})")

                if not any(isinstance(node, ast.ClassDef) and node.name == "Meta" for node in ast.walk(tree_node)):
                    raise ValueError("Invalid module: 'class Meta' not found!")

                filename = url.split("/")[-1]
                if not filename.endswith(".py"): filename += ".py"
                
                path = Path(self.loader.community_path) / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(code, encoding="utf-8")

                await self.loader.register_module(path, self.mx, is_core=False)
                
                if path.stem not in self.mx.active_modules:
                    raise ValueError("Module failed to start. Check bot logs.")

                return True

            except aiohttp.ClientResponseError as e:
                if e.status == 404:
                    raise ValueError(f"Download failed: Module file not found (404) at {url}")
                if e.status == 403:
                    raise ValueError(f"Download failed: Access forbidden (403). Maybe GitHub rate limit?")
                raise ValueError(f"Download failed: HTTP Error {e.status}")
                
            except aiohttp.ClientConnectorError:
                raise ValueError("Download failed: Could not connect to server. Check your internet!")
                
            except Exception as e:
                if isinstance(e, ValueError): raise
                logger.exception("Installation exploded!")
                raise RuntimeError(f"Unexpected installation error: {str(e)}")

    async def uninstall(
        self, 
        name: str
    ) -> None:
        await self.loader.unload_module(name, self.mx)
        path = Path(self.loader.community_path) / f"{name}.py"
        if path.exists():
            path.unlink()
            logger.success(f"Module {name} unloaded!")


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
                    "editable": not is_forbidden # Инвертируем: если НЕ запрещен, то редактируем
                })
                
            return {"configurable": True, "config": schema_info}
    
    async def get_installed(
        self
    ) -> List[dict[str, Any]]:
        
        installed = []
        
        for m_id, mod in self.mx._bot.active_modules.items():
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