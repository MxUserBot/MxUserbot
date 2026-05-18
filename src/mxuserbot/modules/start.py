from pydantic import BaseModel

from mxc import utils 
from .. import loader
from ..core.langs import Locales


class Strings(BaseModel):
    on_start: str


locales = Locales(
    ru=Strings(
        on_start="<b>✅ | Бот запущен</b><br>Загружено модулей: <code>{count}</code>{errors}"
    ),
    en=Strings(
        on_start="<b>✅ | Bot started</b><br>Loaded modules: <code>{count}</code>{errors}"
    ),
    ua=Strings(
        on_start="<b>✅ | Бот запущено</b><br>Завантажено модулів: <code>{count}</code>{errors}"
    ),
    fr=Strings(
        on_start="<b>✅ | Bot démarré</b><br>Modules chargés: <code>{count}</code>{errors}"
    ),
    de=Strings(
        on_start="<b>✅ | Bot gestartet</b><br>Geladene Module: <code>{count}</code>{errors}"
    ),
    jp=Strings(
        on_start="<b>✅ | ボット起動</b><br>読み込まれたモジュール: <code>{count}</code>{errors}"
    ),
)


class Meta:
    name = "StartMessage"
    description = "send start message"
    tags = ["utility"]
    version = ["1.0.0"]


@loader.tds
class StartMesageModule(loader.Module):
    strings = locales

    @loader.start()
    async def on_start(self, mx):
        count = len(mx.active_modules)

        errors_text = ""
        load_errors = getattr(mx, "all_modules", None) and mx.all_modules._load_errors or []
        if load_errors:
            items = "<br>".join(
                f"⬥ <code>{e['name']}</code>: {e['error']}" for e in load_errors
            )
            errors_text = f"<br><br><b>Load errors:</b><br>{items}"

        if mx.log_room:
            try:
                await utils.answer(
                    mx,
                    self.strings.get("on_start").format(count=count, errors=errors_text),
                    room_id=mx.log_room,
                )
            except Exception:
                pass
