import inspect
from mautrix.types import ImageInfo, MessageEvent
from ...core import loader, utils

class Meta:
    name = "Helper"
    _cls_doc = "Enterprise-grade system information and command assistant."
    version = "2.0.0"
    tags = ["system", "helper"]

@loader.tds
class HelperModule(loader.Module):
    # ВСЕ СТРОКИ НА ПЕНДОССКОМ, СУКА!
    strings = {
        "header": "<b>💠 {name} v{version}</b><br><i>{desc}</i><br><br>",
        "default_desc": "Your elite Matrix intelligence officer.",
        "modules_title": "<b>📦 Available Strategic Assets:</b><br><br>",
        "module_item": (
            "<details>"
            "<summary>▫️ <b>{name}</b></summary>"
            "<i>{desc}</i><br>"
            "⬥ {commands}"
            "</details>"
        ),
        "module_info": "<b>📦 Module:</b> {name}<br><b>ℹ️ Description:</b> {desc}<br>",
        "config_title": "<br><b>⚙️ Strategic Configuration:</b><br>",
        "config_item": "    ⬥ <code>{key}</code>: <i>{desc}</i> (Value: <code>{val}</code>)<br>",
        "config_usage_hint": "<br><i>Modify via: <code>.cfg {name} [key] [value]</code></i><br>",
        "commands_title": "<br><b>🛠 Tactical Commands:</b><br>",
        "cmd_info": "<b>Command:</b> <code>{prefix}{name}</code><br><b>Intel:</b> {desc}",
        "cmd_not_found": "❌ Target <code>{name}</code> is not in our database.",
        "no_desc": "Classified information.",
        "no_cmds": "No active offensive capabilities.",
        "cfg_success": "✅ Parameter <b>{key}</b> for <b>{mod}</b> set to <code>{val}</code>",
        "cfg_fail": "❌ Configuration failed. Invalid data type or key.",
        "mod_not_found": "❌ Unit <b>{name}</b> not found.",
        "info_caption": (
            "<b><u>MxUserBot Core</u></b><br>"
            "🆔 | Tactical Version: <code>{version}</code><br>"
            "👩‍💻 | Development: <a href='https://github.com/PashaHatsune/MxUserbot'>Source</a>"
        )
    }

    @loader.command()
    async def help(self, mx, event: MessageEvent, target: str = ""):
        """[target] | Show list of commands or detailed info"""
        try:
            target_clean = target.lower()

            try:
                found_mod = next(
                    m for m in mx.active_modules.values()
                    if (m.Meta.name if hasattr(m, "Meta") else m.__class__.__name__).lower() == target_clean
                )
                return await self._render_module_help(mx, event, found_mod)
            except StopIteration:
                pass
            try:
                all_cmds = {n.lower(): (m, f) for m in mx.active_modules.values() for n, f in m.commands.items()}
                mod, func = all_cmds[target_clean]
                
                prefix = await mx.get_prefix()
                return await event.reply(self.strings.get("cmd_info").format(
                    prefix=prefix, name=target_clean, desc=inspect.getdoc(func) or self.strings.get("no_desc")
                ))
            except KeyError:
                raise loader.UsageError(self.strings.get("cmd_not_found").format(name=target))

        except (AttributeError, TypeError):
            return await self._render_all_help(mx, event)

    async def _render_all_help(self, mx, event):
        """Собираем полный список модулей"""
        msg = self.strings.get("header").format(
            name="MxUserBot", version=mx.version, desc=self.strings.get("default_desc")
        )
        msg += self.strings.get("modules_title")

        for mod in sorted(mx.active_modules.values(), key=lambda x: (x.Meta.name if hasattr(x, "Meta") else x.__name__)):
            name = mod.Meta.name if hasattr(mod, "Meta") else mod.__class__.__name__
            desc = mod.Meta._cls_doc if hasattr(mod, "Meta") else self.strings.get("no_desc")
            cmds = ", ".join([f"<code>{c}</code>" for c in mod.commands.keys()]) or self.strings.get("no_cmds")
            msg += self.strings.get("module_item").format(name=name, desc=desc, commands=cmds)
        
        await event.reply(msg)

    async def _render_module_help(self, mx, event, mod):
        """Подробная инфа по модулю"""
        name = mod.Meta.name if hasattr(mod, "Meta") else mod.__class__.__name__
        desc = mod.Meta._cls_doc if hasattr(mod, "Meta") else self.strings.get("no_desc")
        prefix = await mx.get_prefix()
        
        msg = self.strings.get("module_info").format(name=name, desc=desc)

        try:
            schema = mod.config._schema
            msg += self.strings.get("config_title")
            for key, cfg in schema.items():
                msg += self.strings.get("config_item").format(
                    key=key, desc=cfg.description or self.strings.get("no_desc"), val=mod.config[key]
                )
            msg += self.strings.get("config_usage_hint").format(prefix=prefix, name=name)
        except (AttributeError, KeyError):
            pass 
        try:
            if mod.commands:
                msg += self.strings.get("commands_title")
                for cmd_name, func in mod.commands.items():
                    msg += f" • <code>{prefix}{cmd_name}</code> — <i>{inspect.getdoc(func) or '...'}</i><br>"
        except AttributeError: pass

        await event.reply(msg)

    @loader.command()
    async def cfg(self, mx, event: MessageEvent, module: str, key: str, value: str):
        """<module> <key> <value> | Configure strategic module settings"""
        try:
            target_mod = next(
                m for m in mx.active_modules.values()
                if (m.Meta.name if hasattr(m, "Meta") else m.__class__.__name__).lower() == module.lower()
            )

            if target_mod.config.set(key, value):
                await event.reply(self.strings.get("cfg_success").format(key=key, mod=module, val=value))
            else:
                raise ValueError("Validation failed")
        
        except StopIteration:
            await event.reply(self.strings.get("mod_not_found").format(name=module))
        except (AttributeError, ValueError, TypeError):
            await event.reply(self.strings.get("cfg_fail").format(key=key))

    @loader.command()
    async def info(self, mx, event: MessageEvent):
        """| Get tactical bot information"""
        await utils.send_image(
            mx=mx, room_id=event.room_id,
            url="mxc://pashahatsune.pp.ua/pjiDYu8KhNf35zAzmVaAoNKijH6gsylj",
            caption=self.strings.get("info_caption").format(version=mx.version),
            file_name="info.png",
            info=ImageInfo(width=600, height=335, mimetype="image/png")
        )