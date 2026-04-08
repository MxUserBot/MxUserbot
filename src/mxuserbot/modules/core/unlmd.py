import asyncio
from pathlib import Path
from ...core import loader

@loader.tds
class MatrixModule(loader.Module):
    strings = {
        "name": "UnloadMod",
        "_cls_doc": "Выгружает и удаляет модуль из community",
        "no_name": "❌ Укажите имя модуля для выгрузки",
        "not_found": "❌ Модуль {name} не найден среди активных",
        "unloaded": "✅ Модуль {name} успешно выгружен и удалён",
        "error": "❌ Ошибка: {err}"
    }

    @loader.command()
    async def unlmd(self, mx, event):
        """!unlmd <имя модуля> — выгружает и удаляет модуль"""
        text = getattr(event.content, "body", "")
        parts = text.split()
        if len(parts) < 2:
            return await mx.client.send_text(event.room_id, self.strings["no_name"])
        
        name = parts[1]

        if name not in mx.all_modules.active_modules:
            return await mx.client.send_text(event.room_id, self.strings["not_found"].format(name=name))
        
        try:
            await mx.all_modules.unload_module(name, mx)

            path = Path(mx.all_modules.community_path) / f"{name}.py"
            if path.exists():
                path.unlink()

            await mx.client.send_text(event.room_id, self.strings["unloaded"].format(name=name))

        except Exception as e:
            await mx.client.send_text(event.room_id, self.strings["error"].format(err=str(e)))