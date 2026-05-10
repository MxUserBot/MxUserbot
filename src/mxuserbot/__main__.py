# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import contextvars
import logging
import sys
import time
import traceback
from ast import List
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
from mautrix.api import HTTPAPI
from mautrix.client import InternalEventType, SyncStream
from mautrix.errors import MatrixConnectionError
from mautrix.types import EventType
from mautrix.util.config import BaseFileConfig, ConfigUpdateHelper, RecursiveDict
from mautrix.util.program import Program
from ruamel.yaml.comments import CommentedMap

from mxc import utils
from mxc.client import MXCClient
from mxc.crypto import BotSASVerification, RocksCryptoStore, RocksCryptoStateStore
from mxc.database import Database
from mxc.fsm import FSM
from mxc.types import InterceptHandler, POLL_RESPONSE, POLL_END


from .core import (
    CallBack,
    Loader,
    MXUS,
)




class Config(BaseFileConfig):
    """
    A placeholder so class Program doesn't complain
    """
    def __init__(self, path: str, base_path: str) -> None:
        super().__init__(path, base_path)
        self._data = RecursiveDict({"logging": {"version": 1}}, CommentedMap)

    def load_base(self) -> RecursiveDict:
        return RecursiveDict({"logging": {"version": 1}}, CommentedMap)

    def load(self) -> None: pass
    def save(self) -> None: pass
    def do_update(self, helper: ConfigUpdateHelper) -> None: pass


class MXBotInterface:
    """A secure wrapper to be passed to modules."""

    def __init__(self, bot: 'MXUserBot'):
        self._bot = bot
        self.version = bot.version

    @property
    def client(self) -> MXCClient:
        return self._bot.client

    @property
    def _current_event(self):
        return self._bot._current_event
    
    @property
    def fsm(self):
        return self._bot.fsm

    @property
    def sas_verifier(self) -> BotSASVerification:
        return self._bot.sas_verifier

    @property
    def _prefixes(self):
        return self._bot._prefixes

    @_prefixes.setter
    def _prefixes(self, value):
        self._bot._prefixes = value


    @property
    def security(self) -> MXUS: # <--- ДОБАВЬ ВОТ ЭТО
        return self._bot.security

    @property
    def _db(self) -> Database:
        if self._bot.security is not None and self._bot.security._is_community_caller():
            raise PermissionError("Community modules cannot access database directly")
        return self._bot._db

    @property
    def active_modules(self) -> dict:
        return self._bot.active_modules


class MXUserBot(Program):
    _current_event = contextvars.ContextVar("current_event")

    """Main userbot class, refactored by a pro."""

    def __init__(self) -> None:
        super().__init__(
            module='main',
            name='MXUserBot',
            description="MXUserbot - Matrix Userbot.",
            command="-",
            version="2.1 | STABLE",
            config_class=Config
        )
        self.fsm = FSM()
        self._ignore_ids = set()

        self.client: Optional[MXCClient] = None
        self._db: Optional[Database] = None
        self.all_modules: Optional[Loader] = None
        self.security: Optional[MXUS] = None
        
        self.active_modules: Dict[str, Any] = {}
        self.interface = MXBotInterface(self)
        self.auth_completed = asyncio.Event()
        
        self.start_time: Optional[int] = None
        self._prefixes: str = "."


    async def _get_core_conf(
        self,
        key: str,
        default: Any = None
    ) -> Any:
        return await self._db.get("core", key, default)


    def _setup_loguru(
        self
    ) -> None:
        logging.basicConfig(
            handlers=[InterceptHandler()], level="WARNING", force=True
        )
        logger.remove()
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>"
        )
        logger.add(sys.stdout, format=log_format, colorize=True)
        self.log = logger.bind(name=self.name)


    async def _init_database(self) -> None:
        master_key = self.security._get_key()
        self._db = Database(master_key)


    async def _setup_logs(self) -> str | None:
        log_room_id = await self._get_core_conf("log_room_id")
        if log_room_id:
            return str(log_room_id)
        return None

    async def _init_logs_background(self) -> None:
        try:
            log_room_id = await self._get_core_conf("log_room_id")
            if log_room_id:
                return

            target_name = "[LOGS] | MX-USERBOT"
            rooms = await self.client.get_joined_rooms()

            async def check_name(rid):
                try:
                    st = await self.client.get_state_event(rid, EventType.ROOM_NAME)
                    return rid if st and st.get("name") == target_name else None
                except Exception: return None

            found = await asyncio.gather(*[check_name(r) for r in rooms])
            log_room_id = next((res for res in found if res), None)

            if not log_room_id:
                self.log.warning("Room not found.. Create new..")
                avatar = "mxc://pashahatsune.pp.ua/hGaNZRrDKOF5HlHjZ8VilRWj5QHFOXoy"
                log_room_id = await self.client.create_room(
                    name=target_name,
                    is_direct=True,
                    initial_state=[
                        {
                            "type": "m.room.avatar",
                            "content": {"url": avatar}
                        }
                    ]
                )
                await self.client.join_room(log_room_id)
                msg_id = await utils.answer(
                    self.interface,
                    """
👋 | This is **MXUserbot**. Thanks for installing!
🔖 | **Default prefix** \[.\]

🤔 | <u>**Getting started**</u>

1. \[Optional\] Verify your bot via SAS verification
2. `help` — list all commands

📦 | <u>**Modules**</u>

1. `ms <name>` — search modules
2. `mdl <name>` — install module
3. `unmd <name>` — remove module
4. `addrepo <url>` — add community repo
5. `cfg <module> <key> <value>` — config module

🌌 | #MxUserbot:matrix.org
                    """,
                    room_id=log_room_id
                )
                await utils.pin_room(self.interface, log_room_id)
                await utils.pin(self.interface, log_room_id, msg_id)

            await self._db.set("core", "log_room_id", str(log_room_id))
            self.log.success(f"Log room ready: {log_room_id}")
        except Exception as e:
            self.log.error(f"Log room setup failed: {e}")


    def prepare(self) -> None:
        super().prepare()
        self.add_startup_actions(self.setup_userbot())


    async def run_web(self):
        from .web.api.main import run_web_server
        await run_web_server(self, 8000)


    async def setup_userbot(self) -> None:
        self._setup_loguru()
        try:
            self.security = MXUS(self)
            await self._init_database()
            self.security._db = self._db
            
            await self.run_web()
            token = await self._get_core_conf("access_token")
            if not token:
                self.log.warning("🔑 | auth not found. Please auth.")
                await self.auth_completed.wait()
                token = await self._get_core_conf("access_token")

            base_url = await self._get_core_conf("base_url")
            username = await self._get_core_conf("username")
            device_id = await self._get_core_conf("device_id")

            self.start_time = int(time.time() * 1000)

            self.client = MXCClient(
                api=HTTPAPI(
                    base_url=base_url
                ),
                crypto=True,
                rate_limit_protect=True
            )
            self.client.api.token = token
            self.client.mxid = username
            self.client.device_id = device_id

            state_store = RocksCryptoStateStore(self._db, username)
            await state_store.load()
            crypto_store = RocksCryptoStore(
                self._db,
                username,
                self.security._get_pickle_key()
            )
            await self.client.init_crypto(crypto_store, state_store)
            self.sas_verifier = self.client.sas_verifier

            while True:
                try:
                    await self.client.whoami()
                    break
                except (MatrixConnectionError, OSError):
                    self.log.error("🌐 | Network unavailable, retrace in 5 seconds...")
                    await asyncio.sleep(5)

            await self.security.init_security()

            await self._setup_logs()
            from .core.log import MXLog
            self.matrix_sink = MXLog(self)
            logger.add(self.matrix_sink.write, level="ERROR")

            self.all_modules = Loader(self._db)
            try:
                await asyncio.wait_for(self.all_modules.register_all(self), timeout=30)
            except asyncio.TimeoutError:
                self.log.error("Module loading timed out")
                raise
            self.active_modules = self.all_modules.active_modules
            
            self._prefixes = await self._get_core_conf("prefix")
            if not self._prefixes:
                await self._db.set(owner="core", key="prefix", value=".")

            cb = CallBack(self)
            self.client.add_event_handler(EventType.ROOM_MEMBER, self.security.gate(cb.invite_cb))
            self.client.add_event_handler(EventType.ROOM_MEMBER, cb.memberevent_cb)
            self.client.add_event_handler(EventType.REACTION, cb._dispatch_event)
            self.client.add_event_handler(EventType.ROOM_REDACTION, cb._dispatch_event)
            self.client.add_event_handler(EventType.STICKER, cb._dispatch_event)
            self.client.add_event_handler(EventType.ROOM_TOMBSTONE, cb._dispatch_event)
            if hasattr(cb, "message_cb"):
                self.client.add_event_handler(EventType.ROOM_MESSAGE, cb.message_cb)
                self.client.add_event_handler(EventType.ROOM_ENCRYPTED, cb.message_cb)

            self.client.add_event_handler(POLL_RESPONSE, cb._dispatch_event)
            self.client.add_event_handler(POLL_END, cb._dispatch_event)

            sync_started = asyncio.Event()
            async def on_sync(_): 
                sync_started.set()
                self.client.remove_event_handler(InternalEventType.SYNC_SUCCESSFUL, on_sync)
            
            self.client.add_event_handler(InternalEventType.SYNC_SUCCESSFUL, on_sync)

            self.client.start(filter_data=None)

            try:
                await asyncio.wait_for(sync_started.wait(), timeout=30)
                self.log.success(f"Userbot Started: {self.client.mxid}")
            except asyncio.TimeoutError:
                self.log.error("Server timeout")

        except Exception:
            raise
        
    async def stop(self) -> None:
        self.log.info("Shutting down...")

        if self.client:
            self.client.stop()

        if hasattr(self, "server"):
            self.server.should_exit = True
            await asyncio.sleep(0.5)

        if self.client and hasattr(self.client, "crypto") and self.client.crypto:
            store = self.client.crypto.crypto_store
            if hasattr(store, "close"):
                await store.close()
            state = self.client.crypto.state_store
            if hasattr(state, "flush"):
                await state.flush()

        if hasattr(self, "_db") and self._db is not None:
            try:
                self._db.close()
            except Exception as e:
                raise

        await super().stop()


if __name__ == "__main__":
    bot = MXUserBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
