# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from __future__ import annotations

from typing import Any

import yaml
from pathlib import Path
from pydantic import BaseModel

LANGS_DIR = Path(__file__).resolve().parent.parent / "langpacks"

_CURRENT = "en"
_FLAT: dict[str, str] = {}
_FALLBACK: dict[str, str] = {}
_GETTER = None
_SETTER = None

LANGS_ORDER = ["ru", "en", "ua", "fr", "de", "jp"]


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    result = {}
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, key))
        elif isinstance(v, str):
            result[key] = v
    return result


_en_path = LANGS_DIR / "en.yaml"
if _en_path.exists():
    with open(_en_path, encoding="utf-8") as f:
        _FALLBACK = _flatten(yaml.safe_load(f) or {})
        _FLAT = dict(_FALLBACK)


def _load(code: str) -> None:
    global _CURRENT, _FLAT
    path = LANGS_DIR / f"{code}.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            _FLAT = _flatten(yaml.safe_load(f) or {})
        _CURRENT = code


class YamlStrings:
    """Единый провайдер строк для core модулей.
    API совместим с Translator (community модули).
    """
    def __init__(self, domain: str = ""):
        self._domain = domain
        self._extra: dict[str, str] = {}

    def _resolve(self, key: str) -> str | None:
        full_key = f"{self._domain}.{key}" if self._domain else key
        if full_key in self._extra:
            return self._extra[full_key]
        val = _FLAT.get(full_key)
        if val is not None:
            return val
        return _FALLBACK.get(full_key)

    def get(self, key: str, default=None) -> str | None:
        val = self._resolve(key)
        return val if val is not None else default

    def __getitem__(self, key: str) -> str:
        val = self._resolve(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, value: str):
        self._extra[key] = value

    def __contains__(self, key) -> bool:
        full_key = f"{self._domain}.{key}" if self._domain else key
        return full_key in self._extra or full_key in _FLAT or full_key in _FALLBACK

    def setdefault(self, key: str, default=None) -> str | None:
        if key in self._extra:
            return self._extra[key]
        val = self._resolve(key)
        if val is not None:
            return val
        self._extra[key] = default
        return default

    def copy(self) -> YamlStrings:
        y = YamlStrings(self._domain)
        y._extra = dict(self._extra)
        return y


STRINGS = YamlStrings()


class Locales(BaseModel):
    ru: Any = None
    en: Any = None
    ua: Any = None
    fr: Any = None
    de: Any = None
    jp: Any = None

    def has(self, lang: str) -> bool:
        return getattr(self, lang, None) is not None

    def first_available(self) -> str | None:
        for lang in LANGS_ORDER:
            if self.has(lang):
                return lang
        return None


class Translator:
    def __init__(self, locales: Locales, lang: str = "en"):
        self._locales = locales
        self._extra: dict[str, str] = {}

    def set_lang(self, lang: str):
        pass

    @staticmethod
    def _get_field(obj, key: str):
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def _resolve(self, key: str) -> str | None:
        lang = current()
        obj = getattr(self._locales, lang, None)
        if obj:
            val = self._get_field(obj, key)
            if val is not None:
                return val
        for lang in LANGS_ORDER:
            obj = getattr(self._locales, lang, None)
            if obj:
                val = self._get_field(obj, key)
                if val is not None:
                    return val
        return None

    def get(self, key: str, default=None) -> str | None:
        if key in self._extra:
            return self._extra[key]
        val = self._resolve(key)
        return val if val is not None else default

    def __getitem__(self, key):
        if key in self._extra:
            return self._extra[key]
        val = self._resolve(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key, value):
        self._extra[key] = value

    def setdefault(self, key, default=None):
        if key in self._extra:
            return self._extra[key]
        val = self._resolve(key)
        if val is not None:
            return val
        self._extra[key] = default
        return default

    def __contains__(self, key):
        return key in self._extra or self._resolve(key) is not None

    def copy(self):
        t = Translator(self._locales)
        t._extra = dict(self._extra)
        return t


async def init(getter, setter) -> None:
    global _GETTER, _SETTER
    _GETTER = getter
    _SETTER = setter
    saved = await getter("lang")
    if saved and saved != "en":
        _load(saved)


def available() -> list[str]:
    return sorted(p.stem for p in LANGS_DIR.glob("*.yaml"))


def current() -> str:
    return _CURRENT


async def switch(code: str) -> bool:
    path = LANGS_DIR / f"{code}.yaml"
    if not path.exists():
        return False
    _load(code)
    if _SETTER:
        await _SETTER("lang", code)
    return True
