import re
import sys
import typing
import inspect
import hashlib
import asyncio
import importlib.util
from pathlib import Path
from functools import wraps
from typing import Annotated

from loguru import logger
from mautrix.types import EventType

from . import utils
from .security import ScopedDatabase
from .types import Module, ConfigValue # для удобства импорта
from .security import SUDO, OWNER, EVERYONE


_MODULE_NAME_BY_HASH: typing.Dict[str, str] = {}

SUDO = SUDO
OWNER = OWNER
EVERYONE = EVERYONE


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
                spec.loader.exec_module(module)
            except Exception as e:
                logger.error(f"[{path.stem}] Execution error: {e}")
                return

            if not hasattr(module, 'Meta'):
                logger.info(f"[{path.stem}] class Meta not found in module. Module not load.")
                return

            module_meta = module.Meta

            required_meta_vars = ["name", "_cls_doc", "tags", "version"]
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