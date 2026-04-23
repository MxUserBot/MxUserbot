import os
import asyncio
from typing import Any

from loguru import logger
from mautrix.api import HTTPAPI
from mautrix.client import Client
from mautrix.crypto import OlmMachine
from mautrix.util.async_db import Database as MautrixDatabase
from mautrix.crypto.store.asyncpg import PgCryptoStateStore, PgCryptoStore

from ..schemas import LoginSchema
from ..constants import CRYPTO_DB_FILENAME, CRYPTO_PICKLE_KEY




class AuthService:
    def __init__(
        self,
        db_filename: str = CRYPTO_DB_FILENAME,
        pickle_key: str = CRYPTO_PICKLE_KEY,
    ) -> None:
        self.db_filename = db_filename
        self.pickle_key = pickle_key

    async def login(self, data: LoginSchema, mx: Any, auth_event: asyncio.Event) -> bool:
        base_url = self._build_base_url(data.mxid)
        db_path = os.path.join(os.getcwd(), self.db_filename)
        crypto_db = MautrixDatabase.create(f"sqlite:///{db_path}")
        temp_client: Client | None = None

        try:
            await crypto_db.start()
            await PgCryptoStore.upgrade_table.upgrade(crypto_db)
            await PgCryptoStateStore.upgrade_table.upgrade(crypto_db)

            state_store = PgCryptoStateStore(crypto_db)
            crypto_store = PgCryptoStore(data.mxid, self.pickle_key, crypto_db)
            temp_client = Client(
                api=HTTPAPI(base_url=base_url),
                state_store=state_store,
                sync_store=crypto_store,
            )

            response = await temp_client.login(
                identifier=data.mxid,
                password=data.password,
                initial_device_display_name="MXUserbot Panel",
            )

            await self._initialize_crypto(
                client=temp_client,
                mxid=data.mxid,
                access_token=response.access_token,
                device_id=response.device_id,
                crypto_store=crypto_store,
                state_store=state_store,
            )
            await self._persist_session(
                mx=mx,
                base_url=base_url,
                mxid=data.mxid,
                access_token=response.access_token,
                device_id=response.device_id,
            )

            auth_event.set()
            return True
        except Exception as exc:
            logger.exception("Auth failed for %s", data.mxid)
            raise ValueError(str(exc)) from exc
        finally:
            if temp_client is not None:
                await temp_client.api.session.close()
            await crypto_db.stop()

    def _build_base_url(self, mxid: str) -> str:
        domain = mxid.split(":")[-1]
        return f"https://{domain}"

    async def _initialize_crypto(
        self,
        *,
        client: Client,
        mxid: str,
        access_token: str,
        device_id: str,
        crypto_store: PgCryptoStore,
        state_store: PgCryptoStateStore,
    ) -> None:
        client.mxid = mxid
        client.device_id = device_id
        client.api.token = access_token
        client.crypto = OlmMachine(client, crypto_store, state_store)
        client.crypto.allow_key_requests = True

        await client.crypto.load()
        if not await crypto_store.get_device_id():
            await crypto_store.put_device_id(device_id)

        await client.crypto.share_keys()
        await crypto_store.put_account(client.crypto.account)

    async def _persist_session(
        self,
        *,
        mx: Any,
        base_url: str,
        mxid: str,
        access_token: str,
        device_id: str,
    ) -> None:
        await mx._db.set("core", "base_url", base_url)
        await mx._db.set("core", "username", mxid)
        await mx._db.set("core", "access_token", access_token)
        await mx._db.set("core", "device_id", device_id)
        await mx._db.set("core", "owner", mxid)
        mx.config.save()
