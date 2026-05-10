# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from pathlib import Path

API_DIR = Path(__file__).resolve().parent
WEB_DIR = API_DIR.parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
ASSETS_DIR = WEB_DIR / "assets"
LOCALE_PATH = API_DIR / "locale.json"
