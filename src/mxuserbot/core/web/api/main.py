import re
import os
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, field_validator
from mautrix.client import Client
from mautrix.api import HTTPAPI
from mautrix.crypto import OlmMachine
from mautrix.util.async_db import Database as MautrixDatabase
from mautrix.crypto.store.asyncpg import PgCryptoStore, PgCryptoStateStore
from fastapi.responses import HTMLResponse

class LoginSchema(BaseModel):
    mxid: str
    password: str

    @field_validator('mxid')
    @classmethod
    def validate_mxid(cls, v: str):
        pattern = r"^@[\w\.\-]+:[\w\.\-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError("Формат: @username:server.com")
        return v


async def auth_logic(data: LoginSchema, bot_instance, auth_event):
    domain = data.mxid.split(":")[-1]
    base_url = f"https://{domain}"
    
    db_path = os.path.join(os.getcwd(), "sekai.db")
    crypto_db = MautrixDatabase.create(f"sqlite:///{db_path}")
    await crypto_db.start()
    
    await PgCryptoStore.upgrade_table.upgrade(crypto_db)
    await PgCryptoStateStore.upgrade_table.upgrade(crypto_db)

    state_store = PgCryptoStateStore(crypto_db)
    crypto_store = PgCryptoStore(data.mxid, "sekai_secret_pickle_key", crypto_db)

    temp_client = Client(
        api=HTTPAPI(base_url=base_url),
        state_store=state_store,
        sync_store=crypto_store
    )

    try:
        resp = await temp_client.login(
            identifier=data.mxid,
            password=data.password,
            initial_device_display_name="Sekai Userbot" 
        )

        temp_client.mxid = data.mxid
        temp_client.device_id = resp.device_id
        temp_client.api.token = resp.access_token

        temp_client.crypto = OlmMachine(temp_client, crypto_store, state_store)
        temp_client.crypto.allow_key_requests = True
        await temp_client.crypto.load()
        
        if not await crypto_store.get_device_id():
            await crypto_store.put_device_id(resp.device_id)
        
        await temp_client.crypto.share_keys() 
        await crypto_store.put_account(temp_client.crypto.account)

        await bot_instance.config.update_db_key("matrix.base_url", base_url)
        await bot_instance.config.update_db_key("matrix.username", data.mxid)
        await bot_instance.config.update_db_key("matrix.access_token", resp.access_token)
        await bot_instance.config.update_db_key("matrix.device_id", resp.device_id)
        await bot_instance.config.update_db_key("matrix.owner", data.mxid)
        bot_instance.config.save()

        await temp_client.api.session.close()
        await crypto_db.stop()

        auth_event.set()
        
        return {"status": "success", "message": "Auth successful."}

    except Exception as e:
        if temp_client: await temp_client.api.session.close()
        await crypto_db.stop()
        raise HTTPException(status_code=401, detail=str(e))

def setup_routes(app: FastAPI, bot_instance, auth_event):
    @app.post("/api/auth")
    async def auth_endpoint(data: LoginSchema = Body(...)):
        return await auth_logic(data, bot_instance, auth_event)
    

    @app.get("/", response_class=HTMLResponse)
    async def get_login_page():
        html_path = os.path.join(os.getcwd(), "src/mxuserbot/core/web/index.html")
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Файл index.html не найден")