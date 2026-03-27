import asyncio
import os
import tempfile
import whisper
from ..core import loader
from nio import RoomGetEventError, DownloadError


@loader.tds
class MatrixModule(loader.Module):
    """Автоматическое распознавание всех голосовых сообщений"""
    
    strings = {
        "name": "Whisper",
        "_cls_doc": "Автоматически переводит все голосовые сообщения в текст",
        "working": "🎙 <i>Распознаю ГС...</i>",
        "transcribed": "<b>🎙 ГС от {}:</b>\n{}",
        "error": "❌ Ошибка Whisper: {}"
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = None

    async def _matrix_start(self, bot):
        self.logger.info("Загрузка модели Whisper...")
        self.model = await asyncio.to_thread(whisper.load_model, "turbo", "cpu")
        self.logger.info("✅ Модель Whisper готова.")

    async def _process_audio(self, bot, event):
        """Внутренний метод для обработки аудио-контента. 
        Принимает только bot и event (у которого есть .room)
        """
        content = event.source.get('content', {})
        mxc_url = content.get("url") or content.get("file", {}).get("url")
        
        if not mxc_url:
            return

        tmp_path = None
        try:
            audio_resp = await bot.client.download(mxc=mxc_url)
            if isinstance(audio_resp, DownloadError):
                self.logger.error(f"Download error: {audio_resp.message}")
                return

            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                tmp.write(audio_resp.body)
                tmp_path = tmp.name

            result = await asyncio.to_thread(self.model.transcribe, tmp_path)
            text = result.get("text", "").strip()

            if text:
                # sender без домена
                sender = event.sender.split(':')[0][1:] 
                await bot.send_text(event.room, self.strings["transcribed"].format(sender, text))

        except Exception as e:
            self.logger.exception("Whisper automatic processing failed")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    async def _matrix_message(self, bot, event):
        """Срабатывает на каждое сообщение (Watcher)"""
        if not self.model:
            return

        # event.room уже добавлен в core/callback.py
        content = event.source.get('content', {})
        
        if content.get("msgtype") == "m.audio":
            self.logger.info(f"Обнаружено ГС в {event.room.room_id}, обрабатываю...")
            await self._process_audio(bot, event)


    @loader.command(name="transcribe")
    async def transcribe_cmd(self, bot, event):
        """[reply] - Распознать конкретное ГС"""
        
        relates_to = event.source.get('content', {}).get('m.relates_to', {})
        reply_to_id = relates_to.get('m.in_reply_to', {}).get('event_id')

        if not reply_to_id:
            return await bot.send_text(event.room, "❌ Ответьте на ГС.")

        resp = await bot.client.room_get_event(event.room.room_id, reply_to_id)
        if isinstance(resp, RoomGetEventError):
            return await bot.send_text(event.room, f"❌ Ошибка: {resp.message}")

        target_event = resp.event
        target_content = target_event.source.get('content', {})
        
        if target_content.get("msgtype") != "m.audio":
            return await bot.send_text(event.room, "❌ Это не аудио.")

        target_event.room = event.room

        await bot.send_text(event.room, self.strings["working"])
        await self._process_audio(bot, target_event)