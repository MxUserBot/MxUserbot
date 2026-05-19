# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import sys
import time
from enum import IntFlag
from functools import wraps

from loguru import logger
from mautrix.errors import MatrixConnectionError

from mxc import utils

from .langs import STRINGS


class SecLevel(IntFlag):
    OWNER = 1
    SUDO = 2
    EVERYONE = 4
    ALL = 7

OWNER = SecLevel.OWNER
SUDO = SecLevel.SUDO
EVERYONE = SecLevel.EVERYONE
ALL = SecLevel.ALL
DEFAULT_PERMISSIONS = SUDO


def _sec(func, flags: int):
    prev = getattr(func, "security", 0)
    func.security = prev | OWNER | flags
    return func


def owner(
    func
):
    return _sec(func, OWNER)


def sudo(
    func
): 
    return _sec(func, SUDO)


def unrestricted(
    func
):
    return _sec(func, EVERYONE)


class ScopedDatabase:
    def __init__(self, raw_db, module_name: str):
        self._raw_db = raw_db
        self._module_name = module_name


    async def get(
        self,
        key: str,
        default=None
    ):
        return await self._raw_db.get(self._module_name, key, default)


    async def set(
        self,
        key: str,
        value
    ):
        return await self._raw_db.set(self._module_name, key, value)


class MXBotInterface:
    """A secure wrapper to be passed to modules.
    
    Dependencies are injected via __init__ or set directly
    on the instance as they become available during startup.
    """

    def __init__(self, *, fsm=None, current_event=None, strings=STRINGS, version="", log_room=None, _bot=None):
        self._client = None
        self._fsm = fsm
        self._security = None
        self._active_modules = {}
        self._current_event = current_event
        self._bot = _bot
        self._prefix_val = "."
        self.strings = strings
        self.version = version

    @property
    def client(self):
        return self._client

    @property
    def log_room(self):
        if self._bot:
            return self._bot.log_room
        return None

    @property
    def security(self):
        return self._security

    @property
    def _prefixes(self):
        return self._prefix_val

    @_prefixes.setter
    def _prefixes(self, value):
        self._prefix_val = value

    @property
    def active_modules(self):
        return self._active_modules


class MXUS:
    def __init__(self, bot):
        self.bot = bot
        self.strings = STRINGS
        self._db = bot._db
        self.owners = set()
        self.sudos = set()
        self.tsec_users =[]
        self._tsec_lock = asyncio.Lock()

        self.key = "mxu.rocksdb/.mxu.key"


    async def init_security(
        self
    ):
        self.mod_perms = await self._db.get("core", "mod_perms", {})
        try:
            resp = await self.bot.client.whoami()
            self.owners.add(resp.user_id)
        except MatrixConnectionError:
            raise
        except Exception as e:
            logger.exception(e)
            raise

        db_owners = await self._db.get("core", "owners",[])
        if isinstance(db_owners, list):
            self.owners.update(db_owners)
        
        db_sudos = await self._db.get("core", "sudos",[])
        if isinstance(db_sudos, list):
            self.sudos.update(db_sudos)
        
        self.tsec_users = await self._db.get("core", "tsec_users",[])
        
        logger.success(f"Security active. Owner: {self.owners}")


    def is_owner(
        self,
        sender_id: str
    ) -> bool:
        return sender_id in self.owners


    def gate(
        self,
        func
    ):
        @wraps(func)
        async def wrapper(event, *args, **kwargs):
            sender = getattr(event, "sender", None)
            if not sender or sender in self.owners:
                return await func(event, *args, **kwargs)
            cfg = getattr(func, "security", DEFAULT_PERMISSIONS)
            has_access, expired = self.check_tsec(sender, func.__name__)
            if cfg & EVERYONE or (cfg & SUDO and sender in self.sudos) or has_access:
                return await func(event, *args, **kwargs)
            user_expired = [r for r in expired if r.get("target") == sender]
            if user_expired:
                await self._notify_tsec_expired(user_expired)
            return
        return wrapper


    def check_tsec(
        self,
        sid,
        cmd
    ):
        cur = time.time()
        expired = [r for r in self.tsec_users if r.get("expires") and r["expires"] <= cur]
        self.tsec_users = [r for r in self.tsec_users if not r.get("expires") or r["expires"] > cur]
        result = any(r["target"] == sid and r["command"] == cmd for r in self.tsec_users)
        return result, expired


    async def _notify_tsec_expired(self, entries: list) -> None:
        for r in entries:
            room_id = r.get("room_id")
            target = r.get("target")
            cmd_name = r.get("command", "?")
            if not room_id or not target:
                continue
            name = target.split(":")[0]
            text = self.strings.get("security.temp_expired").format(name=name, cmd=cmd_name)
            try:
                await utils.answer(self.bot, text, room_id=room_id)
            except Exception:
                logger.opt(exception=True).warning("Failed to send tsec expiry notice")


    async def check_access(
        self,
        sender: str,
        func,
        cmd_name: str
    ) -> bool:
            if sender in self.owners:
                return True

            if sender in self.sudos:
                return True

            cfg = getattr(func, "security", DEFAULT_PERMISSIONS)
            if cfg & EVERYONE:
                return True
            
            if (cfg & SUDO) and (sender in self.sudos):
                return True
            
            user_allowed = self.mod_perms.get(sender,[])
            if not user_allowed:
                return False

            if cmd_name in user_allowed:
                return True
                
            mod_class = getattr(func, "module_class_name", None)
            
            if not mod_class: 
                instance = getattr(func, "__self__", None)
                if instance:
                    mod_class = instance.__class__.__name__

            if mod_class and mod_class.lower() in user_allowed:
                return True

            cur = time.time()
            return any(
                r["target"] == sender and 
                r["command"] == cmd_name and 
                (not r.get("expires") or r["expires"] > cur)
                for r in self.tsec_users
            )
    
    def _get_key(self) -> bytes:
        import os
        from cryptography.fernet import Fernet
        
        if not os.path.exists(self.key):
            os.makedirs(os.path.dirname(self.key), exist_ok=True)
            logger.warning("🔑 | Generate new DB key...")
            key = Fernet.generate_key()
            with open(self.key, "wb") as f:
                f.write(key)
        else:
            with open(self.key, "rb") as f:
                key = f.read().strip()
        
        os.chmod(os.path.dirname(self.key), 0o700)
        os.chmod(self.key, 0o600)
        return key

    def _get_pickle_key(self) -> str:
        return ensure_pickle_key()


def ensure_pickle_key(path: str = "mxu.rocksdb/.mxu.pickle_key") -> str:
    import os, secrets

    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        logger.warning("🔑 | Generate new olm-pickle key...")
        key = secrets.token_hex(32)
        with open(path, "w") as f:
            f.write(key)
    else:
        with open(path) as f:
            key = f.read().strip()

    os.chmod(os.path.dirname(path), 0o700)
    os.chmod(path, 0o600)
    return key
