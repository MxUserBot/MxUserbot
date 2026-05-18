# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import inspect
import re
from functools import wraps

from loguru import logger
from mautrix.types import EventType

from .. import utils as cutils
from .constants import SUDO, EVERYONE
from .utils import _parse_cron



def on(event_type: EventType):
    def decorator(func):
        func.is_event_handler = True
        func.handled_event_type = event_type
        return func
    return decorator


def watcher(regex: str, security=EVERYONE):
    def decorator(func):
        func.is_watcher = True
        func.regex = re.compile(regex, re.IGNORECASE)
        func.security = security
        return func
    return decorator


def command(name=None, aliases: list = None, security=SUDO):
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


def start():
    def decorator(func):
        func.is_start_handler = True
        return func
    return decorator


def cron(expr_or_interval: str):
    def decorator(func):
        func.is_cron = True
        func.cron_interval = _parse_cron(expr_or_interval)
        return func
    return decorator


def _collect_commands(cls, paths):
    import pathlib, importlib.util, sys

    mod_file = pathlib.Path(sys.modules[cls.__module__].__file__).parent

    if isinstance(paths, str):
        scan_dir = (mod_file / paths.lstrip("/")).resolve()
        if not scan_dir.exists():
            return
        files = sorted(scan_dir.glob("[!_]*.py"))
    else:
        files = [mod_file / p.lstrip("/") for p in paths]

    parent_pkg = cls.__module__.rpartition(".")[0]

    for f in files:
        if not f.exists():
            continue
        try:
            rel = f.parent.relative_to(mod_file)
            pkg = f"{parent_pkg}.{'.'.join(rel.parts)}"
        except ValueError:
            pkg = parent_pkg
        full_name = f"{pkg}.{f.stem}"
        spec = importlib.util.spec_from_file_location(full_name, f)
        if not spec or not spec.loader:
            continue
        m = importlib.util.module_from_spec(spec)
        m.__package__ = pkg
        m.__name__ = full_name
        spec.loader.exec_module(m)
        for name in dir(m):
            obj = getattr(m, name)
            if callable(obj) and getattr(obj, "is_command", False):
                setattr(cls, name, obj)


def tds(cls=None, collect=None):
    if cls is not None and collect is None:
        return _tds_impl(cls)

    def wrapper(actual_cls):
        if collect:
            _collect_commands(actual_cls, collect)
        return _tds_impl(actual_cls)
    return wrapper


def _tds_impl(cls):
    if not hasattr(cls, 'strings'):
        cls.strings = {}

    is_legacy = isinstance(cls.strings, dict)

    if is_legacy:
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

            for command_, func_ in cutils.get_commands(cls).items():
                proccess_decorators("_cmd_doc_", command_)
                try:
                    func_.__doc__ = self.strings[f"_cmd_doc_{command_}"]
                except AttributeError:
                    func_.__func__.__doc__ = self.strings[f"_cmd_doc_{command_}"]

            return await self._internal_init._old_(self, *args, **kwargs)

        _internal_init._old_ = cls._internal_init
        cls._internal_init = _internal_init

        for command_, func in cutils.get_commands(cls).items():
            cmd_doc = func.__doc__
            if cmd_doc:
                cls.strings.setdefault(f"_cmd_doc_{command_}", inspect.cleandoc(cmd_doc))

    return cls
