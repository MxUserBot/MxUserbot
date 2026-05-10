# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from .auth import AuthController
from .modules import ModuleController
from .pages import PageController
from .repos import RepoController
from .system import SystemController

__all__ = [
    "AuthController",
    "ModuleController",
    "PageController",
    "RepoController",
    "SystemController",
]
