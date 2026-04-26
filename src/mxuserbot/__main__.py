import os
import sys
import time
import logging
import asyncio
import traceback
import contextvars
from ast import List
from typing import Optional, Dict, Any

from loguru import logger
from mautrix.api import HTTPAPI
from mautrix.client import Client
from mautrix.crypto import OlmMachine
from mautrix.util.program import Program
from mautrix.client import InternalEventType
from ruamel.yaml.comments import CommentedMap
from mautrix.errors import MatrixConnectionError
from mautrix.types import MessageEvent, EventType
from mautrix.util.async_db import Database as MautrixDatabase
from mautrix.crypto.store.asyncpg import PgCryptoStore, PgCryptoStateStore
from mautrix.util.config import BaseFileConfig, ConfigUpdateHelper, RecursiveDict

from .core import utils
from .core.loader import Loader, FSM
from .core.callback import CallBack
from .core.security import SekaiSecurity
from .core.types import BotSASVerification, InterceptHandler
from ..database import Database, AsyncSessionWrapper


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

    _current_event = contextvars.ContextVar("current_event")
    

    def __init__(self, bot: 'MXUserBot'):
        self._bot = bot
        self.version = bot.version

        
        self._get_prefix_func = bot.get_prefix
        self._should_ignore_event_func = bot.should_ignore_event


    @property
    def client(self) -> Client:
        return self._bot.client


    @property
    def fsm(self):
        return self._bot.fsm

    @property
    def sas_verifier(self) -> BotSASVerification:
        return self._bot.sas_verifier


    @property
    def active_modules(self) -> dict:
        return self._bot.active_modules


    async def get_prefix(self) -> str:
        return await self._get_prefix_func()


    def should_ignore_event(self, evt: MessageEvent) -> bool:
        return self._should_ignore_event_func(evt)

class MXUserBot(Program):
    """Main userbot class, refactored by a pro."""

    def __init__(self) -> None:
        super().__init__(
            module='main',
            name='MXUserBot',
            description="MXUserbot - matrix userbot.",
            command="-",
            version="2.0 | BETA",
            config_class=Config
        )
        self.fsm = FSM()
        self._ignore_ids = set()

        self.client: Optional[Client] = None
        self._db: Optional[Database] = None
        self.all_modules: Optional[Loader] = None
        self.security: Optional[SekaiSecurity] = None
        
        self.active_modules: Dict[str, Any] = {}
        self.interface = MXBotInterface(self)
        self.auth_completed = asyncio.Event()
        
        self.start_time: Optional[int] = None
        self._prefixes: List[str] = ["."]


    async def _get_core_conf(
        self,
        key: str,
        default: Any = None
    ) -> Any:
        return await self._db.get("core", key, default)


    async def get_prefix(
        self
    ) -> str:
        return self._prefixes[0] if self._prefixes else "."


    def should_ignore_event(
        self,
        evt: MessageEvent
    ) -> bool:
        if not evt.content.body:
            return True
        
        return evt.timestamp < (self.start_time - 10000)


    def _setup_loguru(
        self
    ) -> None:
        logging.basicConfig(
            handlers=[InterceptHandler()], level="INFO", force=True
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
        session_wrapper = AsyncSessionWrapper()
        self._db = Database(session_wrapper)
        try:
            await self._db._sw.init_db()
        except Exception as e:
            raise e
        self.config.db = self._db


    async def _setup_logs(self) -> str:
        log_room_id = await self._get_core_conf("log_room_id")
        if log_room_id:
            return str(log_room_id)

        target_name = "[LOGS] | MX-USERBOT"        
        rooms = await self.client.get_joined_rooms()
        
        async def check_name(rid):
            try:
                st = await self.client.get_state_event(rid, EventType.ROOM_NAME)
                return rid if st and st.get("name") == target_name else None
            except: return None

        found = await asyncio.gather(*[check_name(r) for r in rooms])
        log_room_id = next((res for res in found if res), None)

        if not log_room_id:
            self.log.warning("Room not found.. Create new..")
            avatar = "mxc://pashahatsune.pp.ua/hGaNZRrDKOF5HlHjZ8VilRWj5QHFOXoy"
            log_room_id = await self.client.create_room(
                name=target_name, is_direct=True,
                initial_state=[{"type": "m.room.avatar", "content": {"url": avatar}}]
            )
            await self.client.join_room(log_room_id)
            msg_id = await utils.answer(self.interface, "✅ | Log room initialized.", room_id=log_room_id)
            await utils.pin_room(self.interface, log_room_id)
            await utils.pin(self.interface, log_room_id, msg_id)

        await self._db.set("core", "log_room_id", str(log_room_id))
        return str(log_room_id)


    async def _init_crypto(
        self,
        username: str,
        device_id: str
    ):
            db_path = os.path.join(os.getcwd(), "sekai.db")
            self.crypto_db = MautrixDatabase.create(f"sqlite:///{db_path}")
            await self.crypto_db.start()

            await PgCryptoStore.upgrade_table.upgrade(self.crypto_db)
            await PgCryptoStateStore.upgrade_table.upgrade(self.crypto_db)

            self.state_store = PgCryptoStateStore(self.crypto_db)
            self.crypto_store = PgCryptoStore(username, "sekai_secret_pickle_key", self.crypto_db)

            self.client.state_store = self.state_store
            self.client.sync_store = self.crypto_store 

            self.client.crypto = OlmMachine(self.client, self.crypto_store, self.state_store)
            self.client.crypto.allow_key_requests = True
            await self.client.crypto.load()

            orig_decrypt = self.client.crypto._decrypt_olm_event

            async def hooked_decrypt(evt):
                dec = await orig_decrypt(evt)
                if dec and "m.key.verification" in (dec.type.t if hasattr(dec.type, "t") else str(dec.type)):
                    asyncio.create_task(self.sas_verifier.handle_decrypted_event(dec))
                return dec
            
            self.client.crypto._decrypt_olm_event = hooked_decrypt

            if not await self.crypto_store.get_device_id():
                await self.crypto_store.put_device_id(self.client.device_id)
                await self.client.crypto.share_keys()


    async def starts_with_command(
        self,
        body: str
    ) -> bool:
        return body.startswith(tuple(self._prefixes))


    async def _setup_security(self) -> None:
        self.security = SekaiSecurity(self)
        await self.security.init_security()


    def prepare_log(self) -> None:
        self._setup_loguru()


    def prepare(self) -> None:
        super().prepare()
        self.add_startup_actions(self.run_api())
        self.add_startup_actions(self.setup_userbot())


    async def run_api(self):
        from .core.web.api.main import run_web_server
        await run_web_server(self, 8000)


    async def setup_userbot(
        self
    ) -> None:
        try:
            await self._init_database()
            
            token = await self._get_core_conf("access_token")
            if not token:
                self.log.warning("🔑 | auth not found. Please auth.")
                await self.auth_completed.wait()
                token = await self._get_core_conf("access_token")

            base_url = await self._get_core_conf("base_url")
            username = await self._get_core_conf("username")
            device_id = await self._get_core_conf("device_id")

            self.client = Client(api=HTTPAPI(base_url=base_url))
            self.client.api.token, self.client.mxid, self.client.device_id = token, username, device_id

            await self._init_crypto(username, device_id)
            self.sas_verifier = BotSASVerification(self.client)

            while True:
                try:
                    await self.client.whoami()
                    break
                except (MatrixConnectionError, OSError):
                    self.log.error("🌐 | Network unavailable, retrace in 5 seconds...")
                    await asyncio.sleep(5)

            await self._setup_logs()
            from .core.log import MXLog
            self.matrix_sink = MXLog(self)
            logger.add(
                self.matrix_sink.write,
                level="WARNING"
            )
            
            await self._setup_security()
            
            self.all_modules = Loader(self._db)
            await self.all_modules.register_all(self.interface)
            self.active_modules = self.all_modules.active_modules
            
            self._prefixes = await self._get_core_conf("prefix")
            if not self._prefixes:
                await self._db.set(
                    owner="core",
                    key="prefix",
                    value=["."]
                )

            cb = CallBack(self)
            self.client.add_event_handler(EventType.ROOM_MEMBER, self.security.gate(cb.invite_cb))
            self.client.add_event_handler(EventType.ROOM_MEMBER, cb.memberevent_cb)

            self.client.add_event_handler(EventType.REACTION, lambda e: cb._dispatch_event(EventType.REACTION, e))
            self.client.add_event_handler(EventType.ROOM_REDACTION, lambda e: cb._dispatch_event(EventType.ROOM_REDACTION, e))
            self.client.add_event_handler(EventType.ROOM_TOMBSTONE, lambda e: cb._dispatch_event(EventType.ROOM_TOMBSTONE, e))
            if hasattr(cb, "message_cb"):
                self.client.add_event_handler(EventType.ROOM_MESSAGE, cb.message_cb)

            self.start_time = int(time.time() * 1000)
            
            sync_started = asyncio.Event()
            async def on_sync(_): 
                sync_started.set()
                self.client.remove_event_handler(InternalEventType.SYNC_SUCCESSFUL, on_sync)
            
            self.client.add_event_handler(InternalEventType.SYNC_SUCCESSFUL, on_sync)
            
            sync_result = self.client.start(filter_data=None)
            if asyncio.iscoroutine(sync_result):
                asyncio.create_task(sync_result)

            try:
                await asyncio.wait_for(sync_started.wait(), timeout=30)
                self.log.success(f"Userbot Started: {self.client.mxid}")
            except asyncio.TimeoutError:
                self.log.error("Server timeout")

        except Exception as e:
            raise e
        
    async def stop(
        self
    ) -> None:
            self.log.info("Shutting down gracefully...")

            if self.client:
                self.client.stop()

            if hasattr(self, "server"):
                self.server.should_exit = True
                await asyncio.sleep(0.5)

            if hasattr(self, "crypto_db"):
                await self.crypto_db.stop()

            if self._db and hasattr(self._db, "_sw"):
                try:
                    await self._db._sw.engine.dispose() 
                except:
                    pass

            await super().stop()


if __name__ == "__main__":
    bot = MXUserBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()