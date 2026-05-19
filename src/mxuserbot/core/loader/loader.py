# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import importlib.util
import inspect
import sys
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from mxc import utils

from .constants import _MODULE_NAME_BY_HASH
from .utils import _calc_module_hash, _check_community_source
from ..security import ScopedDatabase
from ..module import Module, ConfigValue
from ..langs import STRINGS
from .repo import RepoManager




class Loader:
    def __init__(self, db_wrapper):
        self._db = db_wrapper
        self.strings = STRINGS
        self.active_modules: Dict[str, object] = {}
        self.module_path = Path(__file__).resolve().parents[2]
        self.core_path = self.module_path / "modules"
        self.community_path = self.module_path / "community"
        self._bot = None
        self._update_check_task: asyncio.Task | None = None
        self._update_check_interval = 21600

        self._background_tasks: set[asyncio.Task] = set()
        self.command_registry: Dict[str, Dict[str, Any]] = {}
        self._load_errors: List[Dict[str, str]] = []

    def _record_error(self, name: str, error: str) -> None:
        self._load_errors.append({"name": name, "error": str(error)})

    async def register_all(self, bot) -> List[Dict[str, str]]:
        self._load_errors = []
        self._bot = bot
        for p in [self.core_path, self.community_path]:
            p.mkdir(parents=True, exist_ok=True)
        await self._load_from_directory(self.core_path, bot, is_core=True)
        await self._load_from_directory(self.community_path, bot, is_core=False)
        logger.info(f"Load modules: {len(self.active_modules)}.")
        self._start_update_checker()
        return self._load_errors

    async def check_updates_now(self) -> list[dict[str, Any]]:
        if not self._bot:
            return []
        rm = RepoManager(self._bot, self._db)
        rm.loader = self
        return await rm.check_updates()

    async def _update_check_loop(self):
        await asyncio.sleep(120)
        last_notify = 0.0
        pending: dict[str, dict] = {}
        while True:
            try:
                updates = await self.check_updates_now()
                for u in updates:
                    pending[u["module_id"]] = u
                now = time.time()
                if pending and (now - last_notify) >= 86400:
                    sorted_updates = sorted(pending.values(), key=lambda x: x["name"].lower())
                    for u in sorted_updates:
                        logger.warning(
                            f"[Updater] {u['name']}: {u['current']} \u2192 {u['available']} "
                            f"(repo: {u['repo_url']})"
                        )
                    msg = "<b>🔄 | Доступны обновления модулей:</b><br><br>" + "<br>".join(
                        f"⬥ <code>{u['name']}</code>: {u['current']} \u2192 <b>{u['available']}</b>"
                        for u in sorted_updates[:10]
                    )
                    if self._bot and hasattr(self._bot, "log_room") and self._bot.log_room:
                        try:
                            await utils.answer(
                                self._bot.interface if hasattr(self._bot, "interface") else self._bot,
                                msg,
                                room_id=self._bot.log_room,
                            )
                        except Exception:
                            pass
                    last_notify = now
                    pending.clear()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"[Updater] check failed: {exc}")
            try:
                await asyncio.sleep(self._update_check_interval)
            except asyncio.CancelledError:
                break

    def _start_update_checker(self):
        if self._update_check_task and not self._update_check_task.done():
            self._update_check_task.cancel()
        self._update_check_task = asyncio.create_task(self._update_check_loop())

    async def _load_from_directory(self, path: Path, bot, is_core: bool) -> None:
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
            _raw_prefix = await utils.get_prefix(mx)
            prefix = next((str(p) for p in _raw_prefix if p), "")
            meta = getattr(mod, "Meta", None)
            name = getattr(meta, "name", mod_name)
            desc = getattr(meta, "description", "—")
            version = getattr(meta, "version", "")
            lines = [self.strings.get("loader.help_name").format(name=name)]
            if version:
                lines[0] += self.strings.get("loader.help_name_version").format(version=version)
            else:
                lines[0] += "<br>"
            lines.append(self.strings.get("loader.help_desc").format(desc=desc))
            if hasattr(mod, "config") and hasattr(mod.config, "_schema"):
                lines.append(self.strings.get("loader.help_config_title"))
                for key, cfg_val in mod.config._schema.items():
                    lines.append(self.strings.get("loader.help_config_item").format(
                        key=key, desc=cfg_val.description or "—", val=mod.config[key]))
            commands = getattr(mod, "commands", {})
            if commands:
                lines.append(self.strings.get("loader.help_commands_title"))
                for cmd_name, func in commands.items():
                    cmd_desc = (func.__doc__ or "—").replace("<", "&lt;").replace(">", "&gt;")
                    lines.append(self.strings.get("loader.help_command_item").format(prefix=prefix, cmd=cmd_name, desc=cmd_desc))
            await utils.answer(mx, "".join(lines), event=event)
        try:
            await _inner()
        except Exception as e:
            logger.error(f"show_module_help error for {filename}: {e}")

    async def register_module(self, path: Path, bot, is_core: bool = False):
        subfolder = "core" if is_core else "community"
        module_name = f"src.mxuserbot.{subfolder}.{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(path))
            if not spec or not spec.loader:
                return
            if not is_core:
                try:
                    _check_community_source(path.read_text("utf-8"), path.stem)
                except PermissionError as e:
                    logger.warning(f"[{path.stem}] {e}")
                    self._record_error(path.stem, str(e))
                    return
            module = importlib.util.module_from_spec(spec)
            module.__package__ = f"src.mxuserbot.{subfolder}"
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                logger.error(f"[{path.stem}] Execution error: {e}")
                sys.modules.pop(module_name, None)
                self._record_error(path.stem, str(e))
                return
            if not hasattr(module, 'Meta'):
                logger.info(f"[{path.stem}] class Meta not found")
                return
            module_meta = module.Meta
            if not self._validate_meta(module_meta, path.stem):
                return
            cls = self._find_module_cls(module, module.__name__)
            if not cls:
                logger.warning(f"[{path.stem}] Class '*Module' not found")
                return
            short_name = path.stem
            if not is_core and self._check_name_conflict(short_name, cls, module_meta.name):
                return
            await self._init_and_start(cls, module_meta, short_name, bot, is_core, spec)
        except Exception as e:
            logger.exception(f"Error loading {path.name}")
            self._record_error(path.stem, str(e))

    async def register_package(self, pkg_dir: Path, bot, is_core: bool = False):
        subfolder = "core" if is_core else "community"
        pkg_name = f"src.mxuserbot.{subfolder}.{pkg_dir.name}"
        short_name = pkg_dir.name
        ok = False
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
            if not is_core:
                try:
                    _check_community_source(init_file.read_text("utf-8"), short_name)
                    for py_file in pkg_dir.rglob("*.py"):
                        _check_community_source(py_file.read_text("utf-8"), py_file.stem)
                except PermissionError as e:
                    logger.warning(f"[{short_name}] {e}")
                    self._record_error(short_name, str(e))
                    return
            pkg_module = importlib.util.module_from_spec(init_spec)
            pkg_module.__package__ = pkg_name
            pkg_module.__path__ = [str(pkg_dir)]
            sys.modules[pkg_name] = pkg_module
            init_spec.loader.exec_module(pkg_module)
            for py_file in sorted(pkg_dir.rglob("*.py")):
                if py_file == init_file:
                    continue
                rel = py_file.relative_to(pkg_dir)
                sub_name = f"{pkg_name}.{rel.with_suffix('').as_posix().replace('/', '.')}"
                if sub_name in sys.modules:
                    continue
                sub_spec = importlib.util.spec_from_file_location(sub_name, str(py_file))
                if not sub_spec or not sub_spec.loader:
                    continue
                sub_mod = importlib.util.module_from_spec(sub_spec)
                parent_parts = rel.parent.as_posix()
                sub_mod.__package__ = f"{pkg_name}.{parent_parts.replace('/', '.')}" if parent_parts != '.' else pkg_name
                sys.modules[sub_name] = sub_mod
                try:
                    sub_spec.loader.exec_module(sub_mod)
                except Exception as e:
                    logger.error(f"[{short_name}] Submodule '{sub_name}': {e}")
                    sys.modules.pop(sub_name, None)
            if not hasattr(pkg_module, 'Meta'):
                logger.info(f"[{short_name}] class Meta not found in package")
                return
            module_meta = pkg_module.Meta
            if not self._validate_meta(module_meta, short_name):
                return
            cls, cls_source = None, None
            for mod_name, mod in list(sys.modules.items()):
                if mod_name == pkg_name or mod_name.startswith(f"{pkg_name}."):
                    cls = self._find_module_cls(mod, mod_name)
                    if cls:
                        cls_source = mod
                        break
            if not cls:
                logger.warning(f"[{short_name}] Class '*Module' not found in package")
                return
            if not is_core and self._check_name_conflict(short_name, cls, module_meta.name):
                return
            cls_spec = None
            if cls_source and hasattr(cls_source, '__spec__'):
                cls_spec = cls_source.__spec__
            await self._init_and_start(cls, module_meta, short_name, bot, is_core, cls_spec or init_spec)
            ok = True
        except Exception as e:
            logger.exception(f"Error package import {pkg_dir.name}")
            self._record_error(short_name, str(e))
        finally:
            if not ok:
                self._cleanup_package_modules(pkg_name)

    def _validate_meta(self, module_meta, short_name: str) -> bool:
        for req in ("name", "description", "tags", "version"):
            val = getattr(module_meta, req, None)
            if not val or not str(val).strip():
                logger.error(f"[{short_name}] Meta '{req}' is missing or empty")
                return False
        return True

    def _check_name_conflict(self, short_name: str, cls, meta_name: str) -> bool:
        if short_name in self.active_modules:
            return True
        for mod in self.active_modules.values():
            if mod.__class__.__name__ == cls.__name__:
                logger.warning(f"[{short_name}] class '{cls.__name__}' conflict")
                return True
            if mod.Meta.name == meta_name:
                logger.warning(f"[{short_name}] name '{meta_name}' conflict")
                return True
        return False

    def _find_module_cls(self, module, module_name: str):
        for attr_name in dir(module):
            if "Module" in attr_name:
                cls = getattr(module, attr_name)
                if inspect.isclass(cls) and cls.__module__ == module_name:
                    return cls
        return None

    async def _init_and_start(self, cls, module_meta, short_name, bot, is_core, spec):
        cls.Meta = module_meta
        instance = await self._init_instance(cls, module_meta, short_name, bot, is_core, spec)
        self.active_modules[short_name] = instance
        task = asyncio.create_task(self._finalize_module_startup(instance, bot, short_name))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

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
                self.command_registry[cmd_name] = {"module": instance, "func": func}
                for alias in getattr(func, "aliases", []):
                    self.command_registry[alias] = self.command_registry[cmd_name]
        instance._cron_tasks = []
        for attr_name in dir(instance):
            attr = getattr(instance, attr_name)
            if callable(attr) and getattr(attr, "is_cron", False):
                instance._cron_tasks.append(attr)
        instance._start_handlers = []
        for attr_name in dir(instance):
            attr = getattr(instance, attr_name)
            if callable(attr) and getattr(attr, "is_start_handler", False):
                instance._start_handlers.append(attr)
        self._apply_metadata(instance, spec)
        return instance

    def _cleanup_package_modules(self, pkg_name: str) -> None:
        to_delete = [m for m in list(sys.modules) if m == pkg_name or m.startswith(f"{pkg_name}.")]
        for m in to_delete:
            sys.modules.pop(m, None)

    async def unload_module(self, name: str, bot) -> bool:
        if name not in self.active_modules:
            return False
        instance = self.active_modules[name]
        if getattr(instance, "_is_core", False):
            raise RuntimeError(f"core module '{name}' cannot be unloaded")
        for task in getattr(instance, "_cron_tasks", []):
            if isinstance(task, asyncio.Task):
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

    async def _finalize_module_startup(self, instance, bot, name):
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
            logger.error(f"Module {name} startup failed: {e}")
            self._record_error(name, str(e))
            self.active_modules.pop(name, None)

    async def _cron_loop(self, mx, func, instance):
        try:
            interval = func.cron_interval
            while True:
                await asyncio.sleep(interval)
                await func(mx)
        except asyncio.CancelledError:
            pass

    def _apply_metadata(self, instance, spec) -> None:
        try:
            with open(spec.origin, 'r', encoding='utf-8') as f:
                source = f.read()
            instance.__source__ = source
            instance.__module_hash__ = _calc_module_hash(source)
            instance.__origin__ = spec.origin
            _MODULE_NAME_BY_HASH[instance.__module_hash__] = instance.__class__.__name__
        except Exception:
            instance.__module_hash__ = "unknown"
