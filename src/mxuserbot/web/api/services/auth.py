# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote

import aiohttp
from loguru import logger
from mautrix.api import HTTPAPI, Method
from mautrix.client import Client
from mautrix.crypto import OlmMachine
from mautrix.types import LoginResponse

from mxc.crypto import RocksCryptoStateStore, RocksCryptoStore
from ..schemas import LoginSchema
from ....core.security import ensure_pickle_key


class AuthService:
    _pending_sso: dict[str, dict] = {}

    def __init__(
        self,
        pickle_key: str | None = None,
    ) -> None:
        self.pickle_key = pickle_key or ensure_pickle_key()

    async def login(self, data: LoginSchema, mx: Any, auth_event: asyncio.Event) -> bool:
        base_url = await self._discover_homeserver(data.mxid)
        temp_client: Client | None = None
        state_store: RocksCryptoStateStore | None = None
        crypto_store: RocksCryptoStore | None = None

        try:
            state_store = RocksCryptoStateStore(mx._db, data.mxid)
            await state_store.load()
            crypto_store = RocksCryptoStore(mx._db, data.mxid, self.pickle_key)
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
            if crypto_store is not None:
                await crypto_store.close()
            if state_store is not None:
                await state_store.close()

    async def init_sso(self, mxid: str, callback_url: str) -> dict:
        domain = mxid.split(":")[-1]
        hs_url = await self._discover_homeserver(mxid)

        headers = {"User-Agent": HTTPAPI.default_ua}
        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(
                    f"{hs_url}/_matrix/client/v3/login",
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("SSO check for %s: got %s from %s", domain, resp.status, hs_url)
                        return {"available": False}
                    data = await resp.json()
            except Exception as exc:
                logger.warning("SSO check for %s: request failed %s", domain, exc)
                return {"available": False}

        flows = [f["type"] for f in data.get("flows", [])]
        if "m.login.sso" not in flows:
            return {"available": False}

        state = uuid.uuid4().hex
        self._pending_sso[state] = {
            "hs_url": hs_url,
            "mxid": mxid,
            "created_at": datetime.utcnow().timestamp(),
        }
        self._cleanup_pending()

        redirect_url = f"{callback_url}?state={state}"
        sso_url = (
            f"{hs_url}/_matrix/client/v3/login/sso/redirect"
            f"?redirectUrl={quote(redirect_url)}"
        )

        return {"available": True, "redirect_url": sso_url}

    async def complete_sso(
        self,
        state: str,
        login_token: str,
        mx: Any,
        auth_event: asyncio.Event,
    ) -> None:
        pending = self._pending_sso.pop(state, None)
        if not pending:
            raise ValueError("Invalid or expired SSO state")

        hs_url = pending["hs_url"]
        temp_client: Client | None = None
        state_store: RocksCryptoStateStore | None = None
        crypto_store: RocksCryptoStore | None = None

        try:
            temp_client = Client(
                api=HTTPAPI(base_url=hs_url),
                state_store=None,
                sync_store=None,
            )

            resp = await temp_client.api.request(
                Method.POST,
                "/_matrix/client/v3/login",
                {
                    "type": "m.login.token",
                    "token": login_token,
                    "initial_device_display_name": "MXUserbot Panel",
                },
                sensitive=True,
            )
            response = LoginResponse.deserialize(resp)
            actual_mxid = response.user_id

            state_store = RocksCryptoStateStore(mx._db, actual_mxid)
            await state_store.load()
            crypto_store = RocksCryptoStore(mx._db, actual_mxid, self.pickle_key)
            temp_client.state_store = state_store
            temp_client.sync_store = crypto_store

            await self._initialize_crypto(
                client=temp_client,
                mxid=actual_mxid,
                access_token=response.access_token,
                device_id=response.device_id,
                crypto_store=crypto_store,
                state_store=state_store,
            )
            await self._persist_session(
                mx=mx,
                base_url=hs_url,
                mxid=actual_mxid,
                access_token=response.access_token,
                device_id=response.device_id,
            )

            auth_event.set()
        except Exception as exc:
            logger.exception("SSO auth failed")
            raise ValueError(str(exc)) from exc
        finally:
            if temp_client is not None:
                await temp_client.api.session.close()
            if crypto_store is not None:
                await crypto_store.close()
            if state_store is not None:
                await state_store.close()

    async def _discover_homeserver(self, mxid: str) -> str:
        domain = mxid.split(":")[-1] if ":" in mxid else mxid
        try:
            url = await Client.discover(domain)
            if url is not None:
                homeserver = str(url).rstrip("/")
                logger.info("Discovered homeserver for %s: %s", domain, homeserver)
                return homeserver
            logger.warning("Well-known not found for %s", domain)
        except Exception as exc:
            logger.warning("Well-known discovery failed for %s: %s", domain, exc)
        return f"https://{domain}"

    async def _initialize_crypto(
        self,
        *,
        client: Client,
        mxid: str,
        access_token: str,
        device_id: str,
        crypto_store: RocksCryptoStore,
        state_store: RocksCryptoStateStore,
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

    def _cleanup_pending(self) -> None:
        now = datetime.utcnow().timestamp()
        expired = [
            k for k, v in self._pending_sso.items()
            if now - v.get("created_at", 0) > 600
        ]
        for k in expired:
            self._pending_sso.pop(k, None)
