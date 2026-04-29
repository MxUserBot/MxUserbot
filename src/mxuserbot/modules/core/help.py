from typing import Any

from mautrix.types import ImageInfo, MessageEvent
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...core import loader, utils


class Meta:
    name = "HelperModule"
    description = "helper Centre"
    version = "2.1.0"
    dependencies = ["patchlib"]
    tags = ["helper"]


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
                raise ValueError("Insufficient configuration parameters.")
            return {
                "module_name": parts[0].lower(),
                "key": parts[1],
                "value": parts[2]
            }
        return v


class HelpPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    query: str = Field(default="")

    @model_validator(mode='before')
    @classmethod
    def parse_help(cls, v: Any):
        if isinstance(v, str):
            return {"query": v.strip()}
        return v if v is not None else {"query": ""}


@loader.tds
class HelperModule(loader.Module):
    strings = {
        "header": "<b>💠 | {name}</b><br><i>{desc}</i><br><br>",
        "default_desc": "Helper Center",
        "modules_title": "<b>Available modules:</b><br><br>",
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
        "cmd_info": "<b>Command:</b> <code>{prefix}{name}</code><br><b>Description:</b> <i>{desc}</i>",
        "cmd_not_found": "❌ | <b>Lookup Failed:</b> Command or module <code>{name}</code> not found.",
        "no_desc": "No description available",
        "no_cmds": "No commands configured",
        "mod_not_found": "❌ | <b>Lookup Failed:</b> Module <code>{name}</code> not found in registry.",
        "mod_no_cfg": "❌ | <b>Config Error:</b> Module <code>{name}</code> does not support configuration.",
        "cfg_success": "✅ | <b>Config Updated:</b> <code>{key}</code> for <b>{mod}</b> set to <code>{val}</code>",
        "cfg_fail": "❌ | <b>Config Update Failed:</b> Invalid key or validation error for <code>{key}</code>.",
        "info_caption": (
            "<b><u>MxUserBot Enterprise Protocol</u></b><br>"
            "🆔 | Version: <code>{version}</code><br>"
            "👩‍💻 | source: "
            "<a href='https://github.com/PashaHatsune/MxUserbot'>Repository</a><br>"
        )
    }


    @loader.command()
    async def help(
        self, 
        mx, 
        event: MessageEvent, 
        payload: HelpPayload = HelpPayload()
    ):
        """[module/command] - Display system operations manual or specific module documentation"""
        prefix = await mx.get_prefix()
        target = payload.query.lower()

        if not target:
            msg = self.strings["header"].format(
                name="MxUserBot",
                desc=self.strings["default_desc"]
            )
            msg += self.strings["modules_title"]

            sorted_modules = sorted(
                mx.active_modules.values(), 
                key=lambda x: (x.Meta.name if hasattr(x, "Meta") else x.__class__.__name__)
            )

            for mod in sorted_modules:
                name = mod.Meta.name if hasattr(mod, "Meta") else mod.__class__.__name__
                desc = mod.Meta.description if hasattr(mod, "Meta") else self.strings["no_desc"]
                
                if hasattr(mod, "commands") and mod.commands:
                    cmds = ", ".join([f"<code>{c}</code>" for c in mod.commands.keys()])
                else:
                    cmds = self.strings["no_cmds"]

                msg += self.strings["module_item"].format(
                    name=name,
                    desc=desc,
                    commands=cmds
                )
            
            return await utils.answer(mx, msg)

        target_mod = mx.active_modules.get(target)
        if not target_mod:
            for mod in mx.active_modules.values():
                mod_name = (mod.Meta.name if hasattr(mod, "Meta") else mod.__class__.__name__).lower()
                if mod_name == target:
                    target_mod = mod
                    break

        if target_mod:
            name = target_mod.Meta.name if hasattr(target_mod, "Meta") else target_mod.__class__.__name__
            desc = target_mod.Meta.description if hasattr(target_mod, "Meta") else self.strings["no_desc"]
            
            msg = self.strings["module_info"].format(name=name, desc=desc)

            if hasattr(target_mod, "config") and hasattr(target_mod.config, "_schema"):
                msg += self.strings["config_title"]
                for key, cfg_val in target_mod.config._schema.items():
                    current_val = target_mod.config[key]
                    msg += self.strings["config_item"].format(
                        key=key,
                        desc=cfg_val.description or self.strings["no_desc"],
                        val=current_val
                    )
                msg += self.strings["config_usage_hint"].format(prefix=prefix, name=target)

            if hasattr(target_mod, "commands") and target_mod.commands:
                msg += self.strings["commands_title"]
                for cmd_name, func in target_mod.commands.items():
                    msg += f" • <code>{prefix}{cmd_name}</code> — <i>{func.__doc__ or self.strings['no_desc']}</i><br>"
            
            return await utils.answer(mx, msg)

        for mod in mx.active_modules.values():
            if hasattr(mod, "commands") and target in mod.commands:
                func = mod.commands[target]
                doc = func.__doc__ or self.strings["no_desc"]

                res = self.strings["cmd_info"].format(
                    prefix=prefix,
                    name=target,
                    desc=doc
                )
                return await utils.answer(mx, res)

        await utils.answer(mx, self.strings["cmd_not_found"].format(name=target))


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


    @loader.command()
    async def info(self, mx, event: MessageEvent):
        """Display system diagnostic card"""
        await utils.send_image(
            mx=mx, 
            room_id=event.room_id,
            url="mxc://pashahatsune.pp.ua/pjiDYu8KhNf35zAzmVaAoNKijH6gsylj",
            caption=self.strings["info_caption"].format(version=mx.version),
            file_name="info.png",
            info=ImageInfo(width=600, height=335, mimetype="image/png")
        )