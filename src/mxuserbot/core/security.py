# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import ast
import sys
import time
from enum import IntFlag
from functools import wraps

from loguru import logger
from mautrix.errors import MatrixConnectionError

from mxc import utils


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
COMM_MARKERS = ("/mxuserbot/community/",)


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


class MXUS:
    def __init__(self, bot):
        self.bot = bot
        self._db = bot._db
        self.owners = set()
        self.sudos = set()
        self.tsec_users =[] 

        self.comm_markers = ("/mxuserbot/community/",)
        self.comm_marker = self.comm_markers[0]
        self._in_is_community = False
        self.key = "mxu.rocksdb/.mxu.key"
        
        self.forbidden_api =[

        ]
        self.forbidden_core =[
            "login", "logout", "logout_all", "create_device_msc4190",
            "add_dispatcher", "remove_dispatcher"
        ]
        self.forbidden_attrs = ["crypto", "crypto_enabled", "_bot", "device_id"]
        
        self.all_forbidden = set(self.forbidden_api + self.forbidden_core + self.forbidden_attrs)
        
        self.forbidden_imports = {
            "sys", "ctypes", "importlib",
            "shutil", "socket", "pty", "builtins",
        }


    async def init_security(
        self
    ):
        self.mod_perms = await self._db.get("core", "mod_perms", {})
        try:
            resp = await self.bot.client.whoami()
            self.owners.add(resp.user_id)
        except MatrixConnectionError as e:
            raise e
        except Exception as e:
            logger.exception(e)
            sys.exit(1)

        db_owners = await self._db.get("core", "owners",[])
        if isinstance(db_owners, list):
            self.owners.update(db_owners)
        
        db_sudos = await self._db.get("core", "sudos",[])
        if isinstance(db_sudos, list):
            self.sudos.update(db_sudos)
        
        self.tsec_users = await self._db.get("core", "tsec_users",[])
        
        logger.success(f"Security active. Owner: {self.owners}")

        self._enable_firewall()


    def _is_community_caller(
        self
    ) -> bool:
        if self._in_is_community:
            return False
        self._in_is_community = True
        try:
            f = sys._getframe(2)
            fn = f.f_code.co_filename.replace("\\", "/")
            return any(marker in fn for marker in self.comm_markers)
        except Exception:
            return False
        finally:
            self._in_is_community = False


    def _enable_firewall(
        self
    ):
        fs_blocklist = ["mxu.rocksdb", "/mxuserbot/core/", "/modules/core/"]
        
        def _extract_paths(event, args):
            if event in ("open", "os.open"):
                return [str(args[0])]
            if event in ("os.remove",):
                return [str(args[0])]
            if event in ("os.rename",):
                return [str(args[0]), str(args[1])]
            if event in ("os.chmod", "os.chown", "os.listdir", "os.scandir", "os.mkdir"):
                return [str(args[0])]
            return []

        def core_audit_hook(event, args):
            if event in ("compile", "sys._getframe"):
                if event == "compile":
                    source, filename = args
                    if (
                        filename
                        and isinstance(filename, str)
                        and any(marker in filename.replace("\\", "/") for marker in self.comm_markers)
                    ):
                        self._audit_code(source, filename)
                return

            if not self._is_community_caller():
                return

            if event == "import":
                blocked = ["mxuserbot.modules.core", "mxuserbot.core.security"]
                if any(args[0] == b or args[0].startswith(f"{b}.") for b in blocked):
                    raise PermissionError(f"Core import forbidden: {args[0]}")

            if event.startswith("ctypes"):
                raise PermissionError("Memory access denied")

            if event in ("subprocess.Popen",):
                raise PermissionError("Subprocess is forbidden for community modules")

            paths = _extract_paths(event, args)
            if paths:
                joined = " ".join(p.replace("\\", "/").lower() for p in paths)
                if any(r in joined for r in fs_blocklist):
                    raise PermissionError("no")
                if event in ("open", "os.open") and len(args) > 1:
                    mode = args[1]
                    import os as _os
                    write_flags = _os.O_WRONLY | _os.O_RDWR | _os.O_CREAT | _os.O_TRUNC | _os.O_APPEND
                    if isinstance(mode, int) and (mode & write_flags):
                        raise PermissionError("Write access denied")
                    if isinstance(mode, str) and any(m in mode for m in "wax+"):
                        raise PermissionError("Write access denied")
        
        sys.addaudithook(core_audit_hook)


    def _audit_code(
        self,
        source,
        filename
    ):
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in self.all_forbidden:
                    raise PermissionError(f"Forbidden attribute '{node.attr}'")
                
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        base_module = alias.name.split('.')[0]
                        if base_module in self.forbidden_imports:
                            raise PermissionError(f"Forbidden import '{alias.name}'")
                
                if isinstance(node, ast.ImportFrom) and node.module:
                    base_module = node.module.split('.')[0]
                    if base_module in self.forbidden_imports:
                        raise PermissionError(f"Forbidden import '{node.module}'")

                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "__import__"}:
                        raise PermissionError(f"{node.func.id}() is forbidden")
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr in {"eval", "exec", "__import__"}:
                            raise PermissionError(f"{node.func.attr}() is forbidden")
                        if node.func.attr == "getattr":
                            for arg in node.args:
                                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                    if arg.value in self.all_forbidden:
                                        raise PermissionError(f"getattr bypass attempt for '{arg.value}'")

        except SyntaxError:
            raise PermissionError("Syntax Error")


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
            if not sender or sender in self.owners: return await func(event, *args, **kwargs)
            cfg = getattr(func, "security", DEFAULT_PERMISSIONS)
            if cfg & EVERYONE or (cfg & SUDO and sender in self.sudos) or self.check_tsec(sender, func.__name__):
                return await func(event, *args, **kwargs)
            expired = getattr(self, '_just_expired', [])
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
        self._just_expired = expired
        self.tsec_users = [r for r in self.tsec_users if not r.get("expires") or r["expires"] > cur]
        return any(r["target"] == sid and r["command"] == cmd for r in self.tsec_users)


    async def _notify_tsec_expired(self, entries: list) -> None:
        for r in entries:
            room_id = r.get("room_id")
            target = r.get("target")
            cmd_name = r.get("command", "?")
            if not room_id or not target:
                continue
            name = target.split(":")[0]
            text = f"⏰ | {name}, ваше время истекло. теперь вы не можете юзать команду .{cmd_name}"
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
        if self._is_community_caller():
            raise PermissionError("no")

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
        if self._is_community_caller():
            raise PermissionError("no")
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
