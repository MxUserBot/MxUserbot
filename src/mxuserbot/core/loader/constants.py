# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html 

from ..security import ALL, EVERYONE, OWNER, SUDO

ALL = ALL
SUDO = SUDO
OWNER = OWNER
EVERYONE = EVERYONE

_MODULE_NAME_BY_HASH: dict[str, str] = {}

FORBIDDEN_CLIENT_ATTRS = frozenset({
    "crypto", "crypto_enabled",
    "login", "logout", "logout_all", "create_device_msc4190",
    "add_dispatcher", "remove_dispatcher", "init_crypto",
    "_bot", "device_id", "sas_verifier",
})
