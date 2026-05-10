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
    version = "2.2.0"
    dependencies = ["patchlib"]
    tags = ["helper"]


from typing import Any

from mautrix.types import MessageEvent
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mxc.exceptions import UsageError
from mxc import utils
from mxc.types import Image
from .. import loader


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



@loader.tds
class HelperModule(loader.Module):
    strings = {
        "header": "<b>💠 | {name}</b><br><i>{desc}</i><br><br>",
        "default_desc": "Helper Center",
        "modules_title": "<b>Available modules (Page {curr}/{total}):</b><br><br>",
        "module_item": (
            "<details>"
            "<summary>▫️ <b>{name}</b></summary>"
            "<i>{desc}</i><br>"
            "⬥ {commands}"
            "</details>"
        ),
        "module_info": "<b>📦 | </b> <code>{name}</code><br><b>ℹ️ | Description:</b> <i>{desc}</i><br><br>",
        "config_title": "<b>⚙️ | Configuration Options:</b><br>",
        "config_item": "    ⬥ <code>{key}</code>: <i>{desc}</i> (Current: <code>{val}</code>)<br>",
        "config_usage_hint": "<br><i>Modify: <code>{prefix}cfg {name} [key] [value]</code></i><br>",
        "commands_title": "<br><b>🛠 | Commands:</b><br>",
        "cmd_not_found": "❌ | <b>Lookup Failed:</b> Command or module <code>{name}</code> not found.",
        "mod_not_found": "❌ | <b>Lookup Failed:</b> Module <code>{name}</code> not found in registry.",
        "mod_no_cfg": "❌ | <b>Config Error:</b> Module <code>{name}</code> does not support configuration.",
        "cfg_success": "✅ | <b>Config Updated:</b> <code>{key}</code> for <b>{mod}</b> set to <code>{val}</code>",
        "cfg_fail": "❌ | <b>Config Update Failed:</b> Invalid key or validation error for <code>{key}</code>.",
        "no_desc": "No description available",
        "no_cmds": "No commands configured",
        "info_caption": (
            "<b><u>✨ | MXUserbot | ✨</u></b><br><br>"
            "🆔 | Version: <code>{version}</code><br>"
            "👩‍💻 | source: "
            "<a href='https://github.com/PashaHatsune/MxUserbot'>Repository</a><br>"
        ),
    }

    def _module_name(self, mod) -> str:
        return getattr(getattr(mod, "Meta", None), "name", mod.__class__.__name__)

    def _module_desc(self, mod) -> str:
        return getattr(getattr(mod, "Meta", None), "description", self.strings["no_desc"])

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

            markup = utils.EmojiKeyBoard(
                rows=[[
                    utils.EmojiButton(emoji="⬅️", data="prev"),
                    utils.EmojiButton(emoji="➡️", data="next"),
                ]],
                callback=on_page,
                data={"page": 0},
                allowed_senders=event.sender,
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
            await utils.answer(
                mx,
                self.strings["cmd_not_found"].format(name=utils.escape_html(target)),
                event=event,
            )
            return

        prefix = await utils.get_prefix(mx)
        name = self._module_name(target_mod)
        desc = self._module_desc(target_mod)
        msg = self.strings["module_info"].format(name=name, desc=desc)

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
                url="mxc://matrix.org/YiqPIkdkkiJqMqizxJQTBqVx",
                caption=self.strings["info_caption"].format(version=mx.version),
                filename="info.png",
                mimetype="image/png",
                w=600,
                h=335,
            ),
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
