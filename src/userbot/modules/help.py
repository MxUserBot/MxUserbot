from ..core import loader

@loader.tds
class MatrixModule(loader.Module):
    strings = {
        "name": "helper",
        "_cls_doc": "Отображает список всех доступных команд и информацию о модулях.",
    }

    @loader.command()
    async def help(self, bot, room, event, args):
        """[команда] - Показать список команд или справку"""

        if not args:
            msg = f"<b>💠 {self.friendly_name}</b>\n"
            msg += f"<i>{self._help()}</i>\n\n"
            
            msg += "<b>Доступные модули:</b>\n"
            for mod in bot.all_modules.active_modules.values():
                msg += f"▫️ <code>{mod.friendly_name}</code> — {mod._help()}\n"
            

            return await bot.send_text(room, msg)

        cmd_name = args.lower()
        for mod in bot.all_modules.active_modules.values():
            if cmd_name in mod.commands:
                doc = mod.strings.get(f"_cmd_doc_{cmd_name}", "Описание отсутствует")
                return await bot.send_text(
                    room, 
                    f"<b>Команда:</b> <code>!{cmd_name}</code>\n"
                    f"<b>Описание:</b> {doc}"
                )
        
        await bot.send_text(room, f"❌ Команда <code>!{cmd_name}</code> не найдена.")