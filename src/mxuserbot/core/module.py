# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import json
import typing
from abc import ABC
from typing import Any, Callable, Optional

from loguru import logger

from ..core import utils

from .langs import STRINGS, Locales, Translator, YamlStrings, current as lang_current


class ModuleConfig:
    def __init__(self, getter_func, setter_func, schema: dict):
        self._getter = getter_func
        self._setter = setter_func
        self._schema = schema
        self._cache = {key: cfg.default for key, cfg in schema.items()}

    async def _load_from_db(self):
        for key, cfg in self._schema.items():
            db_val = await self._getter(key, cfg.default)
            converted = cfg._convert(db_val)
            if converted is not None:
                self._cache[key] = converted

    def __getitem__(self, key):
        return self._cache.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    def set(self, key: str, raw_value: Any) -> bool:
        if key not in self._schema:
            return False
        cfg = self._schema[key]
        try:
            converted = cfg._convert(raw_value)
            if cfg.validator and not cfg.validator(converted):
                return False
            self._cache[key] = converted
            task = asyncio.create_task(self._setter(key, converted))
            task.add_done_callback(lambda t: logger.error(f"Config write failed for {key}: {t.exception()}") if t.exception() else None)
            return True
        except Exception as e:
            logger.error(f"Config set error for {key}: {e}")
            return False

    async def set_async(self, key: str, raw_value: Any) -> bool:
        if key not in self._schema:
            return False
        cfg = self._schema[key]
        try:
            converted = cfg._convert(raw_value)
            if cfg.validator and not cfg.validator(converted):
                return False
            self._cache[key] = converted
            await self._setter(key, converted)
            return True
        except Exception as e:
            logger.error(f"Config set_async error for {key}: {e}")
            return False

    def get_missing_required(self) -> typing.Optional[str]:
        for key, cfg in self._schema.items():
            if cfg.required:
                val = self._cache.get(key)
                if val is None or val == "NONE" or (isinstance(val, str) and not val.strip()):
                    return key
        return None

    def get_description(self, key: str) -> str:
        return self._schema[key].description if key in self._schema else STRINGS.get("module.no_description")


class ConfigValue:
    def __init__(
        self,
        default: Any,
        description: str = "",
        validator: Optional[Callable[[Any], bool]] = None,
        forbid: bool = False,
        required: bool = False
    ):
        self.default = default
        self.required = required
        self.description = description
        self.validator = validator
        self.forbid = forbid
        self.type = type(default)

    def _convert(self, val: Any) -> Any:
        if isinstance(val, self.type):
            return val
        if isinstance(val, str):
            if self.type == bool:
                return val.lower() in ("true", "yes", "1", "y", "on")
            if self.type == int:
                return int(val)
            if self.type == float:
                return float(val)
            if self.type == list or self.type == dict:
                return json.loads(val)
        return val


class Module(ABC):
    __origin__ = "<unknown>"
    __module_hash__ = "unknown"
    __source__ = ""

    config = {}
    strings = {}

    async def _internal_init(self, name, db, loader_or_dict, is_core: bool):
        self.name = name
        self._is_core = is_core
        self.enabled = True
        self.logger = logger.bind(name=self.name)

        if is_core:
            self._db = db
            self.loader = loader_or_dict
            self.allmodules = loader_or_dict.active_modules
        else:
            self._db = None
            self.loader = None
            self.allmodules = loader_or_dict

        self._get = db.get
        self._set = db.set

        raw = getattr(self.__class__, "strings", {})
        if isinstance(raw, dict):
            self.strings = raw.copy()
        elif isinstance(raw, Locales):
            self.strings = Translator(raw, lang_current())
        elif isinstance(raw, Translator):
            self.strings = raw.copy()
            self.strings.set_lang(lang_current())
        elif isinstance(raw, YamlStrings):
            self.strings = raw.copy()
        else:
            self.strings = {}
        self.friendly_name = self.strings.get("name") or self.config.get("name") or self.__class__.__name__

        schema = getattr(self.__class__, "config", {})
        if is_core:
            async def _cfg_get(key: str, default=None):
                return await db.get(name, key, default)
            async def _cfg_set(key: str, value):
                return await db.set(name, key, value)
            self.config = ModuleConfig(_cfg_get, _cfg_set, schema)
        else:
            self.config = ModuleConfig(self._get, self._set, schema)
        await self.config._load_from_db()

        self._commands = {}
        for cmd_name, func in utils.get_commands(self.__class__).items():
            self._commands[cmd_name] = getattr(self, func.__name__)

    def _help(self):
        return self.strings.get("description", STRINGS.get("module.no_description_available"))

    @property
    def commands(self):
        return self._commands

    async def _get(self, key, default=None):
        return await self._db.get(self.name, key, default)

    async def _set(self, key, value):
        return await self._db.set(self.name, key, value)

    async def _matrix_start(self, mx):
        pass

    def _matrix_stop(self, mx):
        pass
