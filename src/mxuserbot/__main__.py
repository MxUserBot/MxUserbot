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
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
from mautrix.api import HTTPAPI
from mautrix.client import InternalEventType
from mautrix.errors import MatrixConnectionError
from mautrix.types import EventType
from mautrix.types.filter import Filter, RoomEventFilter, RoomFilter, StateFilter
from mautrix.util.config import BaseFileConfig, ConfigUpdateHelper, RecursiveDict
from mautrix.util.program import Program
from ruamel.yaml.comments import CommentedMap

from mxc import utils
from mxc.client import MXCClient
from mxc.crypto import RocksCryptoStore, RocksCryptoStateStore
from mxc.database import Database
from mxc.fsm import FSM
from mxc.types import InterceptHandler, POLL_RESPONSE, POLL_END


from . import (
    CallBack,
    Loader,
    MXUS,
    MXBotInterface
    
)
from .core.langs import STRINGS, init as lang_init


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



class MXUserBot(Program):
    _current_event = contextvars.ContextVar("current_event")

    """Main userbot class, refactored by a pro."""

    def __init__(self) -> None:
        super().__init__(
            module='main',
            name='MXUserbot',
            description="MXUserbot - Matrix Userbot.",
            command="-",
            version="2.6 | BETA",
            config_class=Config
        )
        self.fsm = FSM()
        self._ignore_ids = set()

        self.client: Optional[MXCClient] = None
        self._db: Optional[Database] = None
        self.all_modules: Optional[Loader] = None
        self.security: Optional[MXUS] = None
        self.log_room = None
        
        self.active_modules: Dict[str, Any] = {}
        self.interface = MXBotInterface(
            fsm=self.fsm,
            current_event=self._current_event,
            version=self.version,
            _bot=self,
        )
        self.auth_completed = asyncio.Event()
        self._ready = asyncio.Event()
        
        self.start_time: Optional[int] = None
        self._prefixes: str = "."


    async def _get_core_conf(
        self,
        key: str,
        default: Any = None
    ) -> Any:
        return await self._db.get("core", key, default)

    async def _set_core_conf(
        self,
        key: str,
        value: Any = None
    ) -> Any:
        return await self._db.set("core", key, value)


    async def _upload_assets(self) -> None:
        assets_dir = Path(__file__).resolve().parent.parent.parent / "assets"

        if not await self._get_core_conf("banner_url"):
            banner = assets_dir / "banner.webp"
            if banner.exists():
                try:
                    url = await utils.upload(self.interface, banner.read_bytes(), mime_type="image/webp")
                    await self._db.set("core", "banner_url", url)
                    self.log.success(f"Banner uploaded: {url}")
                except Exception as e:
                    self.log.error(f"Banner upload failed: {e}")

        if not await self._get_core_conf("room_avatar_url"):
            avatar = assets_dir / "promo" / "miku.gif"
            if avatar.exists():
                try:
                    url = await utils.upload(self.interface, avatar.read_bytes(), mime_type="image/gif")
                    await self._db.set("core", "room_avatar_url", url)
                    self.log.success(f"Room avatar uploaded: {url}")
                except Exception as e:
                    self.log.error(f"Room avatar upload failed: {e}")


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
        print(log_room_id)
        if log_room_id:
            self.log_room = log_room_id
            return str(log_room_id)
        await self._init_logs_background()

    async def _init_logs_background(self) -> None:
        try:
            log_room_id = await self._get_core_conf("log_room_id")

            target_name = "[LOGS] | MX-USERBOT"

            if not log_room_id:
                avatar = await self._get_core_conf("room_avatar_url")
                owners_to_invite = [o for o in self.security.owners if o != self.client.mxid] if self.security.owners else None
                log_room_id = await utils.create_room(
                    self.interface,
                    name=target_name,
                    is_direct=True,
                    invitees=owners_to_invite,
                    avatar_url=avatar

                )
                await utils.join_room(self.interface, log_room_id)
                msg_id = await utils.answer(
                    self.interface,
                    STRINGS.get("main.welcome"),
                    room_id=log_room_id
                )
                await utils.pin(self.interface, log_room_id, msg_id)

            await self._db.set("core", "log_room_id", str(log_room_id))
            self.log_room = str(log_room_id)
            self.log.success(f"Log room ready: {log_room_id}")
        except Exception as e:
            self.log.error(f"Log room setup failed: {e}")

    async def _recreate_log_room(self) -> None:
        self.log.warning("Log room lost, recreating...")
        self.log_room = None
        await self._db.set("core", "log_room_id", None)
        await self._init_logs_background()


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
            self.client.crypto.account.mark_keys_as_published()

            async def _patch_self_sig(dev_self, device_keys, self_signing_key):
                pass

            async def _patch_cross_sig(dev_self, resp, user_id):
                pass

            self.client.crypto._store_device_self_signatures = _patch_self_sig.__get__(
                self.client.crypto, type(self.client.crypto)
            )
            self.client.crypto._store_cross_signing_keys = _patch_cross_sig.__get__(
                self.client.crypto, type(self.client.crypto)
            )

    

            self.sas_verifier = self.client.sas_verifier
            self.interface._sas_verifier = self.sas_verifier

            while True:
                try:
                    await self.client.whoami()
                    break
                except (MatrixConnectionError, OSError):
                    self.log.error("🌐 | Network unavailable, retrace in 5 seconds...")
                    await asyncio.sleep(5)

            await self.security.init_security()
            self.interface._security = self.security
            self.interface._client = self.client
            await lang_init(self._get_core_conf, self._set_core_conf)
            await self._upload_assets()
            await self._setup_logs()
            self.interface._log_room = self.log_room

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
            self.interface._active_modules = self.active_modules

            load_errors = self.all_modules._load_errors
            if load_errors and not self.log_room:
                self.log.warning(f"Module load errors: {load_errors}")

            self._prefixes = await self._get_core_conf("prefix")
            if not self._prefixes:
                await self._db.set(owner="core", key="prefix", value=".")
                self._prefixes = "." 
            self.interface._prefixes = self._prefixes

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

            rooms_count = len(await self.client.get_joined_rooms())
            self.log.info(
                f"Starting initial sync for {rooms_count} rooms "
                f"(filter: timeline_limit=50, lazy_load_members=True)..."
            )

            filter_obj = Filter(
                room=RoomFilter(
                    timeline=RoomEventFilter(limit=50),
                    state=StateFilter(lazy_load_members=True),
                    include_leave=False,
                ),
            )
            self.client.start(filter_data=filter_obj)

            try:
                await asyncio.wait_for(sync_started.wait(), timeout=60)
                self.log.success(f"Userbot Started: {self.client.mxid}")
                self._ready.set()

                for instance in list(self.active_modules.values()):
                    for handler in getattr(instance, "_start_handlers", []):
                        passed = self if instance._is_core else self.interface
                        asyncio.create_task(handler(passed))
            except asyncio.TimeoutError:
                self.log.error("Server timeout")

        except Exception:
            raise
        
    async def stop(self) -> None:
        self.log.info("Shutting down...")

        if self.client:
            self.client.stop()

        if hasattr(self, "_web_server"):
            self._web_server.should_exit = True
        elif hasattr(self, "server"):
            self.server.should_exit = True

        if self.client and hasattr(self.client, "crypto") and self.client.crypto:
            store = self.client.crypto.crypto_store
            if hasattr(store, "close"):
                await store.close()
            state = self.client.crypto.state_store
            if hasattr(state, "flush"):
                await state.flush()

        if hasattr(self, "_db") and self._db is not None:
            try:
                await self._db.flush()
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
