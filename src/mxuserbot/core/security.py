import ast
import sys
import time
from functools import wraps

from loguru import logger
from mautrix.errors import MatrixConnectionError

OWNER = 1 << 0       
SUDO = 1 << 1        
EVERYONE = 1 << 2    
ALL = (1 << 3) - 1   
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


class SekaiSecurity:
    def __init__(self, bot):
        self.bot = bot
        self._db = bot._db
        self.owners = set()
        self.sudos = set()
        self.tsec_users =[] 

        self.comm_marker = "/modules/community/"
        
        self.forbidden_api =[

        ]
        self.forbidden_core =[
            "login", "logout", "logout_all", "create_device_msc4190",
            "add_dispatcher", "remove_dispatcher"
        ]
        self.forbidden_attrs = ["crypto", "crypto_enabled", "api", "device_id"]
        
        self.all_forbidden = set(self.forbidden_api + self.forbidden_core + self.forbidden_attrs)
        
        self.forbidden_imports = {
            "sys", "os", "subprocess", "ctypes", "importlib", 
            "shutil", "socket", "pty", "builtins"
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
        try:
            f = sys._getframe(2)
            fn = f.f_code.co_filename.replace("\\", "/")
            return self.comm_marker in fn
        except: return False


    def _enable_firewall(
        self
    ):
        
        def core_audit_hook(
            event,
            args
        ):
            if event == "compile":
                source, filename = args
                if filename and isinstance(filename, str) and self.comm_marker in filename.replace("\\", "/"):
                    self._audit_code(source, filename)

            if event in ("open", "os.remove", "os.rename", "import", "ctypes.c_call"):
                if self._is_community_caller():
                    if event == "import" and "mxuserbot.modules.core" in args[0]:
                        raise PermissionError(f"Core import forbidden: {args[0]}")
                    
                    if event in ("open", "os.remove", "os.rename"):
                        path_str = " ".join(str(a) for a in args).replace("\\", "/").lower()
                        
                        forbidden_paths =[
                            "sekai.db", ".env", "config.json", 
                            "sekai_secret", "/mxuserbot/core/", "/modules/core/"
                        ]
                        
                        if any(restricted in path_str for restricted in forbidden_paths):
                            raise PermissionError("STRICT BLOCK. Access to core/database files is denied.")

                        if event == "open" and len(args) > 1 and hasattr(args[1], "count") and any(m in args[1] for m in "wax+"):
                            raise PermissionError("Write access denied")

                    if event.startswith("ctypes"):
                        raise PermissionError("Memory access denied")
        
        sys.addaudithook(core_audit_hook)


    def _audit_code(
        self,
        source,
        filename
    ):
        if isinstance(source, bytes):
            source_str = source.decode('utf-8', errors='ignore')
        elif isinstance(source, str):
            source_str = source
        else:
            source_str = ""

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

        except SyntaxError as e:
            raise PermissionError("Syntax Error")
            
        # if "getattr" in source_str:
        #     for word in self.all_forbidden:
        #         if f'"{word}"' in source_str or f"'{word}'" in source_str:
        #             raise PermissionError(f"getattr bypass attempt for '{word}'")


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
            return
        return wrapper


    def check_tsec(
        self,
        sid,
        cmd
    ):
        cur = time.time()
        self.tsec_users =[r for r in self.tsec_users if not r.get("expires") or r["expires"] > cur]
        return any(r["target"] == sid and r["command"] == cmd for r in self.tsec_users)


    async def check_access(
        self,
        sender: str,
        func,
        cmd_name: str
    ) -> bool:
            if sender in self.owners:
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