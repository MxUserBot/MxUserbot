#			__  ____  ___   _               _           _   
#			|  \/  \ \/ / | | |___  ___ _ __| |__   ___ | |_ 
#			| |\/| |\  /| | | / __|/ _ \ '__| '_ \ / _ \| __|
#			| |  | |/  \| |_| \__ \  __/ |  | |_) | (_) | |_ 
#			|_|  |_/_/\_\\___/|___/\___|_|  |_.__/ \___/ \__| 
#
# 🔒      Licensed under the GNU AGPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html


class Meta:
    name = "HelperModule"
    description = "helper Centre"
    version = "2.3.0"
    dependencies = ["patchlib"]
    tags = ["helper"]


from difflib import SequenceMatcher
from typing import Any

from mautrix.types import MessageEvent
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mxc.exceptions import UsageError
from mxc import utils
from ..core import utils as cutils
from mxc.types import Image, EmojiButton
from mxc.utils.keyboard import EmojiKeyBoard
from .. import loader
from ..core.langs import Locales, switch as lang_switch, available as lang_available, current as lang_current


class HelpPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    query: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def parse_help(cls, v: Any):
        if isinstance(v, str):
            return {"query": v.strip()}

        return v if v is not None else {"query": ""}


class CfgPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    module_name: str
    key: str
    value: str

    @model_validator(mode='before')
    @classmethod
    def parse_payload(cls, v: Any):
        if isinstance(v, str):
            parts = v.split(maxsplit=2)
            if len(parts) < 3:
                raise UsageError("Insufficient configuration parameters.")
            return {
                "module_name": parts[0].lower(),
                "key": parts[1],
                "value": parts[2]
            }
        return v


class Strings(BaseModel):
    header: str
    default_desc: str
    modules_title: str
    module_item: str
    module_info: str
    config_title: str
    config_item: str
    config_usage_hint: str
    commands_title: str
    cmd_not_found: str
    mod_suggestions: str
    mod_not_found: str
    mod_no_cfg: str
    cfg_success: str
    cfg_fail: str
    no_desc: str
    no_cmds: str
    info_caption: str
    lang_current: str
    lang_available: str
    lang_switched: str
    lang_not_found: str


locales = Locales(
    ru=Strings(
        header="<b>💠 | {name}</b><br><i>{desc}</i><br><br>",
        default_desc="Helper Center",
        modules_title="<b>Доступные модули (Стр. {curr}/{total}):</b><br><br>",
        module_item="<details><summary>▫️ <b>{name}</b></summary><i>{desc}</i><br>⬥ {commands}</details>",
        module_info="<b>📦 | {name} {version}</b><br>┗ {desc}<br><br>",
        config_title="<b>⚙️ Конфигурация</b><br>",
        config_item="- <code>{key}</code>: <i>{desc}</i> (текущее: <code>{val}</code>)<br>",
        config_usage_hint="┗ Изменить: <code>{prefix}cfg {name} [key] [value]</code><br><br>",
        commands_title="<b>🛠 Команды</b><br>",
        cmd_not_found="❌ | <b>Не найдено:</b> Команда или модуль <code>{name}</code> не найдены.",
        mod_suggestions="<b>🔍 | Не смогли найти по названию.</b> Возможно вы имели ввиду это?<br><br>{suggestions}",
        mod_not_found="❌ | <b>Не найдено:</b> Модуль <code>{name}</code> не найден в реестре.",
        mod_no_cfg="❌ | <b>Ошибка конфигурации:</b> Модуль <code>{name}</code> не поддерживает настройку.",
        cfg_success="✅ | <b>Конфигурация обновлена:</b> <code>{key}</code> для <b>{mod}</b> установлен в <code>{val}</code>",
        cfg_fail="❌ | <b>Ошибка обновления:</b> Неверный ключ или ошибка валидации для <code>{key}</code>.",
        no_desc="Описание недоступно",
        no_cmds="Нет команд",
        info_caption="<b><u>✨ | MXUserbot | ✨</u></b><br><br>🆔 | Версия: <code>{version}</code><br>👩‍💻 | Исходный код: <a href='https://github.com/MxUserBot/MXUserbot'>Repository</a><br>",
        lang_current="🌐 <b>Текущий язык:</b> {code}",
        lang_available="<b>Доступно:</b> {list}",
        lang_switched="✅ <b>Язык переключён на</b> <code>{code}</code>",
        lang_not_found="❌ <b>Язык</b> <code>{code}</code> <b>не найден.</b> Доступно: {list}",
    ),
    en=Strings(
        header="<b>💠 | {name}</b><br><i>{desc}</i><br><br>",
        default_desc="Helper Center",
        modules_title="<b>Available modules (Page {curr}/{total}):</b><br><br>",
        module_item="<details><summary>▫️ <b>{name}</b></summary><i>{desc}</i><br>⬥ {commands}</details>",
        module_info="<b>📦 | {name} {version}</b><br>┗ {desc}<br><br>",
        config_title="<b>⚙️ Configuration</b><br>",
        config_item="- <code>{key}</code>: <i>{desc}</i> (current: <code>{val}</code>)<br>",
        config_usage_hint="┗ Modify: <code>{prefix}cfg {name} [key] [value]</code><br><br>",
        commands_title="<b>🛠 Commands</b><br>",
        cmd_not_found="❌ | <b>Lookup Failed:</b> Command or module <code>{name}</code> not found.",
        mod_suggestions="<b>🔍 | Could not find by name.</b> Did you mean this?<br><br>{suggestions}",
        mod_not_found="❌ | <b>Lookup Failed:</b> Module <code>{name}</code> not found in registry.",
        mod_no_cfg="❌ | <b>Config Error:</b> Module <code>{name}</code> does not support configuration.",
        cfg_success="✅ | <b>Config Updated:</b> <code>{key}</code> for <b>{mod}</b> set to <code>{val}</code>",
        cfg_fail="❌ | <b>Config Update Failed:</b> Invalid key or validation error for <code>{key}</code>.",
        no_desc="No description available",
        no_cmds="No commands configured",
        info_caption="<b><u>✨ | MXUserbot | ✨</u></b><br><br>🆔 | Version: <code>{version}</code><br>👩‍💻 | source: <a href='https://github.com/MxUserBot/MXUserbot'>Repository</a><br>",
        lang_current="🌐 <b>Current language:</b> {code}",
        lang_available="<b>Available:</b> {list}",
        lang_switched="✅ <b>Language switched to</b> <code>{code}</code>",
        lang_not_found="❌ <b>Language</b> <code>{code}</code> <b>not found.</b> Available: {list}",
    ),
    ua=Strings(
        header="<b>💠 | {name}</b><br><i>{desc}</i><br><br>",
        default_desc="Helper Center",
        modules_title="<b>Доступні модулі (Стор. {curr}/{total}):</b><br><br>",
        module_item="<details><summary>▫️ <b>{name}</b></summary><i>{desc}</i><br>⬥ {commands}</details>",
        module_info="<b>📦 | {name} {version}</b><br>┗ {desc}<br><br>",
        config_title="<b>⚙️ Конфігурація</b><br>",
        config_item="- <code>{key}</code>: <i>{desc}</i> (поточне: <code>{val}</code>)<br>",
        config_usage_hint="┗ Змінити: <code>{prefix}cfg {name} [key] [value]</code><br><br>",
        commands_title="<b>🛠 Команди</b><br>",
        cmd_not_found="❌ | <b>Не знайдено:</b> Команду або модуль <code>{name}</code> не знайдено.",
        mod_suggestions="<b>🔍 | Не вдалося знайти за назвою.</b> Можливо, ви мали на увазі це?<br><br>{suggestions}",
        mod_not_found="❌ | <b>Не знайдено:</b> Модуль <code>{name}</code> не знайдено в реєстрі.",
        mod_no_cfg="❌ | <b>Помилка конфігурації:</b> Модуль <code>{name}</code> не підтримує налаштування.",
        cfg_success="✅ | <b>Конфігурацію оновлено:</b> <code>{key}</code> для <b>{mod}</b> встановлено в <code>{val}</code>",
        cfg_fail="❌ | <b>Помилка оновлення:</b> Невірний ключ або помилка валідації для <code>{key}</code>.",
        no_desc="Опис недоступний",
        no_cmds="Немає команд",
        info_caption="<b><u>✨ | MXUserbot | ✨</u></b><br><br>🆔 | Версія: <code>{version}</code><br>👩‍💻 | Вихідний код: <a href='https://github.com/MxUserBot/MXUserbot'>Repository</a><br>",
        lang_current="🌐 <b>Поточна мова:</b> {code}",
        lang_available="<b>Доступно:</b> {list}",
        lang_switched="✅ <b>Мову переключено на</b> <code>{code}</code>",
        lang_not_found="❌ <b>Мову</b> <code>{code}</code> <b>не знайдено.</b> Доступно: {list}",
    ),
    fr=Strings(
        header="<b>💠 | {name}</b><br><i>{desc}</i><br><br>",
        default_desc="Helper Center",
        modules_title="<b>Modules disponibles (Page {curr}/{total}):</b><br><br>",
        module_item="<details><summary>▫️ <b>{name}</b></summary><i>{desc}</i><br>⬥ {commands}</details>",
        module_info="<b>📦 | {name} {version}</b><br>┗ {desc}<br><br>",
        config_title="<b>⚙️ Configuration</b><br>",
        config_item="- <code>{key}</code>: <i>{desc}</i> (actuel: <code>{val}</code>)<br>",
        config_usage_hint="┗ Modifier: <code>{prefix}cfg {name} [key] [value]</code><br><br>",
        commands_title="<b>🛠 Commandes</b><br>",
        cmd_not_found="❌ | <b>Introuvable:</b> Commande ou module <code>{name}</code> introuvable.",
        mod_suggestions="<b>🔍 | Introuvable par nom.</b> Vouliez-vous dire ceci?<br><br>{suggestions}",
        mod_not_found="❌ | <b>Introuvable:</b> Module <code>{name}</code> introuvable dans le registre.",
        mod_no_cfg="❌ | <b>Erreur de config:</b> Le module <code>{name}</code> ne supporte pas la configuration.",
        cfg_success="✅ | <b>Config mise à jour:</b> <code>{key}</code> pour <b>{mod}</b> défini à <code>{val}</code>",
        cfg_fail="❌ | <b>Échec de mise à jour:</b> Clé invalide ou erreur de validation pour <code>{key}</code>.",
        no_desc="Aucune description disponible",
        no_cmds="Aucune commande configurée",
        info_caption="<b><u>✨ | MXUserbot | ✨</u></b><br><br>🆔 | Version: <code>{version}</code><br>👩‍💻 | Code source: <a href='https://github.com/MxUserBot/MXUserbot'>Repository</a><br>",
        lang_current="🌐 <b>Langue actuelle:</b> {code}",
        lang_available="<b>Disponible:</b> {list}",
        lang_switched="✅ <b>Langue changée en</b> <code>{code}</code>",
        lang_not_found="❌ <b>Langue</b> <code>{code}</code> <b>introuvable.</b> Disponible: {list}",
    ),
    de=Strings(
        header="<b>💠 | {name}</b><br><i>{desc}</i><br><br>",
        default_desc="Helper Center",
        modules_title="<b>Verfügbare Module (Seite {curr}/{total}):</b><br><br>",
        module_item="<details><summary>▫️ <b>{name}</b></summary><i>{desc}</i><br>⬥ {commands}</details>",
        module_info="<b>📦 | {name} {version}</b><br>┗ {desc}<br><br>",
        config_title="<b>⚙️ Konfiguration</b><br>",
        config_item="- <code>{key}</code>: <i>{desc}</i> (aktuell: <code>{val}</code>)<br>",
        config_usage_hint="┗ Ändern: <code>{prefix}cfg {name} [key] [value]</code><br><br>",
        commands_title="<b>🛠 Befehle</b><br>",
        cmd_not_found="❌ | <b>Nicht gefunden:</b> Befehl oder Modul <code>{name}</code> nicht gefunden.",
        mod_suggestions="<b>🔍 | Nicht gefunden.</b> Meinten Sie dies?<br><br>{suggestions}",
        mod_not_found="❌ | <b>Nicht gefunden:</b> Modul <code>{name}</code> nicht im Register gefunden.",
        mod_no_cfg="❌ | <b>Konfigurationsfehler:</b> Modul <code>{name}</code> unterstützt keine Konfiguration.",
        cfg_success="✅ | <b>Konfiguration aktualisiert:</b> <code>{key}</code> für <b>{mod}</b> auf <code>{val}</code> gesetzt",
        cfg_fail="❌ | <b>Update fehlgeschlagen:</b> Ungültiger Schlüssel oder Validierungsfehler für <code>{key}</code>.",
        no_desc="Keine Beschreibung verfügbar",
        no_cmds="Keine Befehle konfiguriert",
        info_caption="<b><u>✨ | MXUserbot | ✨</u></b><br><br>🆔 | Version: <code>{version}</code><br>👩‍💻 | Quellcode: <a href='https://github.com/MxUserBot/MXUserbot'>Repository</a><br>",
        lang_current="🌐 <b>Aktuelle Sprache:</b> {code}",
        lang_available="<b>Verfügbar:</b> {list}",
        lang_switched="✅ <b>Sprache gewechselt zu</b> <code>{code}</code>",
        lang_not_found="❌ <b>Sprache</b> <code>{code}</code> <b>nicht gefunden.</b> Verfügbar: {list}",
    ),
    jp=Strings(
        header="<b>💠 | {name}</b><br><i>{desc}</i><br><br>",
        default_desc="Helper Center",
        modules_title="<b>利用可能なモジュール (ページ {curr}/{total}):</b><br><br>",
        module_item="<details><summary>▫️ <b>{name}</b></summary><i>{desc}</i><br>⬥ {commands}</details>",
        module_info="<b>📦 | {name} {version}</b><br>┗ {desc}<br><br>",
        config_title="<b>⚙️ 設定</b><br>",
        config_item="- <code>{key}</code>: <i>{desc}</i> (現在: <code>{val}</code>)<br>",
        config_usage_hint="┗ 変更: <code>{prefix}cfg {name} [key] [value]</code><br><br>",
        commands_title="<b>🛠 コマンド</b><br>",
        cmd_not_found="❌ | <b>見つかりません:</b> コマンドまたはモジュール <code>{name}</code> が見つかりません。",
        mod_suggestions="<b>🔍 | 名前で見つかりませんでした。</b> もしかしてこれですか？<br><br>{suggestions}",
        mod_not_found="❌ | <b>見つかりません:</b> モジュール <code>{name}</code> がレジストリに見つかりません。",
        mod_no_cfg="❌ | <b>設定エラー:</b> モジュール <code>{name}</code> は設定をサポートしていません。",
        cfg_success="✅ | <b>設定を更新しました:</b> <code>{key}</code> を <b>{mod}</b> に <code>{val}</code> として設定",
        cfg_fail="❌ | <b>更新失敗:</b> <code>{key}</code> のキーが無効か検証エラーです。",
        no_desc="説明はありません",
        no_cmds="設定されたコマンドはありません",
        info_caption="<b><u>✨ | MXUserbot | ✨</u></b><br><br>🆔 | バージョン: <code>{version}</code><br>👩‍💻 | ソース: <a href='https://github.com/MxUserBot/MXUserbot'>Repository</a><br>",
        lang_current="🌐 <b>現在の言語:</b> {code}",
        lang_available="<b>利用可能:</b> {list}",
        lang_switched="✅ <b>言語を</b> <code>{code}</code> <b>に切り替えました</b>",
        lang_not_found="❌ <b>言語</b> <code>{code}</code> <b>が見つかりません。</b> 利用可能: {list}",
    ),
)


@loader.tds
class HelperModule(loader.Module):
    strings = locales

    config = {
        "banner_url": loader.ConfigValue(
            default="mxc://matrix.org/YiqPIkdkkiJqMqizxJQTBqVx",
            description="Banner image URL for .info command",
        ),
    }

    def _module_name(self, mod) -> str:
        return getattr(getattr(mod, "Meta", None), "name", mod.__class__.__name__)

    def _module_desc(self, mod) -> str:
        meta = getattr(mod, "Meta", None)
        desc = getattr(meta, "description", None) or ""
        return desc if desc else self.strings["no_desc"]

    def _module_version(self, mod) -> str:
        v = getattr(getattr(mod, "Meta", None), "version", "")
        if isinstance(v, list):
            return "v" + ".".join(str(x) for x in v)
        return "v" + str(v) if v else ""

    @loader.command()
    async def help(self, mx, event: MessageEvent, payload: HelpPayload = HelpPayload()):
        """[module] - Show modules list or detailed module help"""
        target = payload.query.lower()

        if not target:
            all_mods = [
                module
                for module in mx.active_modules.values()
                if getattr(module, "enabled", True)
            ]
            sorted_modules = sorted(all_mods, key=self._module_name)
            page_size = 5
            total_pages = max((len(sorted_modules) + page_size - 1) // page_size, 1)

            rendered = []
            for p in range(total_pages):
                start = p * page_size
                items = sorted_modules[start:start + page_size]

                msg = self.strings["header"].format(
                    name="MxUserBot",
                    desc=self.strings["default_desc"],
                )
                msg += self.strings["modules_title"].format(curr=p + 1, total=total_pages)

                for mod in items:
                    commands = getattr(mod, "commands", {})
                    if commands:
                        cmds = ", ".join([f"<code>{cmd}</code>" for cmd in commands.keys()])
                    else:
                        cmds = self.strings["no_cmds"]
                    msg += self.strings["module_item"].format(
                        name=self._module_name(mod),
                        desc=self._module_desc(mod),
                        commands=cmds,
                    )
                rendered.append(msg)

            if total_pages <= 1:
                await utils.answer(mx, rendered[0], event=event)
                return

            async def on_page(ctx: utils.EmojiCallbackContext) -> None:
                page = ctx.data["page"]
                if ctx.payload == "prev":
                    page = max(0, page - 1)
                elif ctx.payload == "next":
                    page = min(total_pages - 1, page + 1)
                ctx.data["page"] = page
                await ctx.edit(rendered[page])

            markup = EmojiKeyBoard(
                rows=[[
                    EmojiButton(emoji="⬅️", data="prev"),
                    EmojiButton(emoji="➡️", data="next"),
                ]],
                callback=on_page,
                data={"page": 0},
                remove_clicked=False,
            )
            await utils.answer(mx, rendered[0], event=event, reply_markup=markup)
            return

        target_mod = mx.active_modules.get(target)
        if not target_mod:
            for mod in mx.active_modules.values():
                if self._module_name(mod).lower() == target:
                    target_mod = mod
                    break

        if not target_mod:
            suggestions = {}
            for mod in mx.active_modules.values():
                if not getattr(mod, "enabled", True):
                    continue
                mod_name = self._module_name(mod).lower()
                display = self._module_name(mod)

                if mod_name.startswith(target):
                    suggestions[display] = max(suggestions.get(display, 0), 0.95)
                elif target in mod_name:
                    suggestions[display] = max(suggestions.get(display, 0), 0.85)
                else:
                    score = SequenceMatcher(None, target, mod_name).ratio()
                    if score >= 0.65:
                        suggestions[display] = max(suggestions.get(display, 0), score)

                for alias in getattr(mod, "aliases", []):
                    a = alias.lower()
                    if a.startswith(target):
                        suggestions[display] = max(suggestions.get(display, 0), 0.95)
                    elif target in a:
                        suggestions[display] = max(suggestions.get(display, 0), 0.85)
                    else:
                        alias_score = SequenceMatcher(None, target, a).ratio()
                        if alias_score >= 0.65:
                            suggestions[display] = max(suggestions.get(display, 0), alias_score)

            if suggestions:
                ranked = sorted(suggestions.items(), key=lambda x: x[1], reverse=True)
                items = "<br>".join(
                    f"⬥ <code>{cutils.escape_html(n)}</code>" for n, _ in ranked[:5]
                )
                await utils.answer(
                    mx,
                    self.strings["mod_suggestions"].format(suggestions=items),
                    event=event,
                )
                return

            await utils.answer(
                mx,
                self.strings["cmd_not_found"].format(name=cutils.escape_html(target)),
                event=event,
            )
            return

        prefix = await utils.get_prefix(mx)
        name = self._module_name(target_mod)
        desc = self._module_desc(target_mod)
        version = self._module_version(target_mod)
        msg = self.strings["module_info"].format(name=name, version=version, desc=desc)

        if hasattr(target_mod, "config") and hasattr(target_mod.config, "_schema"):
            msg += self.strings["config_title"]
            for key, cfg_val in target_mod.config._schema.items():
                msg += self.strings["config_item"].format(
                    key=key,
                    desc=cfg_val.description or self.strings["no_desc"],
                    val=target_mod.config[key],
                )
            msg += self.strings["config_usage_hint"].format(prefix=prefix, name=target)

        commands = getattr(target_mod, "commands", {})
        if commands:
            msg += self.strings["commands_title"]
            for cmd_name, func in commands.items():
                desc = func.__doc__ or self.strings["no_desc"]
                msg += f" • <code>{prefix}{cmd_name}</code> — <i>{desc}</i><br>"

        await utils.answer(mx, msg, event=event)

    @loader.command()
    async def info(self, mx, event: MessageEvent):
        """System information card"""
        await utils.answer(
            mx,
            room_id=event.room_id,
            media=Image(
                url=self.config["banner_url"],
                caption=self.strings["info_caption"].format(version=mx.version),
                filename="info.png",
                mimetype="image/png",
            ),
        )


    @loader.command()
    async def lang(self, mx, event: MessageEvent):
        """<code> — Switch bot interface language"""
        args = await cutils.get_args(mx, event)
        if not args:
            return await utils.answer(
                mx,
                self.strings.get("lang_current").format(code=lang_current())
                + "<br>"
                + self.strings.get("lang_available").format(list=", ".join(lang_available())),
                event=event,
            )
        if await lang_switch(args[0].lower()):
            await utils.answer(mx, self.strings.get("lang_switched").format(code=lang_current()), event=event)
        else:
            await utils.answer(
                mx, self.strings.get("lang_not_found").format(code=args[0].lower(), list=", ".join(lang_available())), event=event
            )

    @loader.command()
    async def cfg(
        self, 
        mx, 
        event: MessageEvent, 
        payload: CfgPayload
    ):
        """<module> <key> <value> | Modify active module configuration"""
        target_mod = payload.module_name
        module = mx.active_modules.get(target_mod)
        
        if not module:
            for mod in mx.active_modules.values():
                if hasattr(mod, "Meta") and mod.Meta.name.lower() == target_mod:
                    module = mod
                    break

        if not module:
            return await utils.answer(mx, self.strings["mod_not_found"].format(name=target_mod))

        if not hasattr(module, "config") or not hasattr(module.config, "set"):
            return await utils.answer(mx, self.strings["mod_no_cfg"].format(name=target_mod))

        if module.config.set(payload.key, payload.value):
            await utils.answer(mx, self.strings["cfg_success"].format(
                key=payload.key,
                mod=target_mod,
                val=payload.value
            ))
        else:
            await utils.answer(mx, self.strings["cfg_fail"].format(key=payload.key))