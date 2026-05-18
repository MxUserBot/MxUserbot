import asyncio
import atexit
import logging
import os
import random
import signal
import sys
import shutil
from pydantic import BaseModel

from mxc import utils
from .. import loader
from ..core.langs import Locales


class Meta:
    name = "Restart"
    description = "restart"
    version = "1.1.0"
    tags = ["system", "utils"]


class Strings(BaseModel):
    restarting: str
    restarted: str


locales = Locales(
    ru=Strings(
        restarting="<b>🔄 | Выполняю перезагрузку...</b>",
        restarted="<b>✅ | Перезагрузка успешно завершена!</b>",
    ),
    en=Strings(
        restarting="<b>🔄 | Performing restart...</b>",
        restarted="<b>✅ | Restart completed successfully!</b>",
    ),
)


async def _fw_protect():
    await asyncio.sleep(random.randint(1000, 3000) / 1000)

def _get_startup_callback() -> callable:
    def callback(*_):
        uv_path = shutil.which("uv")
    
        os.execl(
            uv_path,
            uv_path,
            "run",
            "-m",
            "src.mxuserbot",
            *sys.argv[1:],
        )

    return callback

def _die():
    if "DOCKER" in os.environ:
        sys.exit(0)
    else:
        try:
            os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)
        except ProcessLookupError:
            sys.exit(0)

def _trigger_restart():
    if "MX_DO_NOT_RESTART" in os.environ:
        print(
            "🔄 Restart loop detected! Exiting to prevent spam.\n"
            "Check your logs for errors immediately after start."
        )
        sys.exit(1)

    logging.getLogger().setLevel(logging.CRITICAL)
    print("🔄 MXUserbot is restarting...")

    os.environ["MX_DO_NOT_RESTART"] = "1"

    if "DOCKER" in os.environ:
        atexit.register(_get_startup_callback())
        sys.exit(0)
    else:
        signal.signal(signal.SIGTERM, _get_startup_callback())
        _die()



@loader.tds
class RestartModule(loader.Module):
    strings = locales

    async def _matrix_start(self, mx):
        if "MX_DO_NOT_RESTART" in os.environ:
            os.environ.pop("MX_DO_NOT_RESTART")
            
        state = await self._get(self.Meta.name, "restart_state")
        
        if state:
            room_id = state.get("room_id")
            msg_id = state.get("msg_id")
            
            if room_id and msg_id:
                try:
                    await utils.answer(
                        mx, 
                        self.strings.get("restarted"), 
                        room_id=room_id, 
                        edit_id=msg_id
                    )
                except Exception as e:
                    raise
            
            await self._set(self.Meta.name, "restart_state", None)


    @loader.command(security=loader.OWNER)
    async def restart(self, mx, event):
        """Перезагрузить юзербота / Restart bot"""
        
        msg_id = await utils.answer(mx, self.strings.get("restarting"), event=event)
        
        await self._set(self.Meta.name, "restart_state", {
            "room_id": event.room_id,
            "msg_id": msg_id
        })
        
        await _fw_protect()
        
        
        _trigger_restart()