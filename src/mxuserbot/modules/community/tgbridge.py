import asyncio
import logging
from telethon import TelegramClient, events
from mautrix.types import MessageEvent, TextMessageEventContent, RoomDirectoryVisibility
from ...core import loader, utils

logger = logging.getLogger("TGBridge")

class Meta:
    name = "TelegramBridge"
    _cls_doc = "Мост с исправленным дублированием после перезагрузки."
    version = "1.4.1"
    dependencies = ["telethon"]
    tags = ["bridge"]

@loader.tds
class TelegramBridgeModule(loader.Module):
    config = {
        "API_ID": 23281546,
        "API_HASH": "1485b7f21956a05dff9fa3bc9e1a2fd0",
        "TARGET_TG_ID": -1003887102880 
    }

    def __init__(self):
        super().__init__()
        self.tg_client = None
        self._mx = None
        self._is_ready = False
        self._last_bridged_text = None
        self.tg_chat_id = None

    async def _matrix_start(self, mx):
        self._mx = mx
        self.tg_chat_id = int(self.config["TARGET_TG_ID"])
        
        await self.prepare_bridge()
        # Запускаем основной процесс
        asyncio.create_task(self.start_bridge())

    async def prepare_bridge(self):
        uid = "default"
        if hasattr(self._mx, "user_id"):
            uid = self._mx.user_id.split(':')[0].replace("@", "")
        
        self.tg_client = TelegramClient(
            f"tg_session_{uid}", 
            int(self.config["API_ID"]), 
            self.config["API_HASH"]
        )

    async def start_bridge(self):
        try:
            await self.tg_client.connect()
            if await self.tg_client.is_user_authorized():
                # 1. Сначала догоняем историю
                await self.sync_tg_history()
                
                # 2. Только ПОСЛЕ истории включаем хендлер новых сообщений
                self.tg_client.add_event_handler(
                    self.on_remote_message, 
                    events.NewMessage(chats=self.tg_chat_id)
                )
                
                # 3. ПОСЛЕ завершения всех процессов помечаем, что мост готов
                # Это предотвратит обработку старых сообщений Matrix как новых
                self._is_ready = True
                logger.info(f"Мост запущен и синхронизирован.")
            else:
                logger.error("Телеграм не авторизован.")
        except Exception as e:
            logger.error(f"Ошибка старта: {e}")

    async def sync_tg_history(self):
        """Получение пропущенных сообщений из Telegram"""
        last_id = await self._get("last_tg_msg_id")
        if not last_id:
            async for msg in self.tg_client.iter_messages(self.tg_chat_id, limit=1):
                await self._set("last_tg_msg_id", msg.id)
            return

        # Берём сообщения после последнего ID
        new_messages = []
        async for msg in self.tg_client.iter_messages(self.tg_chat_id, min_id=int(last_id), reverse=True):
            new_messages.append(msg)
        
        if new_messages:
            logger.info(f"Синхронизация {len(new_messages)} сообщений из TG...")
            for msg in new_messages:
                await self.on_remote_message(msg)

    async def on_remote_message(self, event):
        """TG -> Matrix"""
        if not event.text: return

        # Проверка эха (если сообщение ушло из Matrix в TG только что)
        if event.out and event.text == self._last_bridged_text:
            return

        room_id = await self._get("synced_room")
        if not room_id: return

        try:
            sender = await event.get_sender()
            name = getattr(sender, 'first_name', 'User')
            
            # Важно: Формируем plain-текст так же, как он будет выглядеть в проверке эха
            plain_text = f"[{name}]: {event.text}"
            html_text = f"<b>[{name}]</b>: {event.text}"
            
            await self._mx.client.send_text(
                str(room_id), 
                plain_text, 
                html=html_text
            )
            
            await self._set("last_tg_msg_id", event.id)
        except Exception as e:
            logger.error(f"Ошибка пересылки в Matrix: {e}")

    @loader.command()
    async def tgsync(self, mx, event: MessageEvent):
        """Синхронизация комнаты"""
        try:
            entity = await self.tg_client.get_entity(self.tg_chat_id)
            title = getattr(entity, 'title', 'TG_Group')
            new_room_id = await mx.client.create_room(
                name=f"TG | {title}",
                visibility=RoomDirectoryVisibility.PRIVATE,
            )
            await self._set("synced_room", str(new_room_id))
            async for msg in self.tg_client.iter_messages(self.tg_chat_id, limit=1):
                await self._set("last_tg_msg_id", msg.id)
            await mx.answer(f"🔗 Связано с <code>{new_room_id}</code>")
        except Exception as e:
            await mx.answer(f"❌ Ошибка: {e}")

    async def _matrix_message(self, mx, event: MessageEvent):
        """Matrix -> TG"""
        # Если мост еще синхронизирует историю, игнорируем старые сообщения из Matrix
        if not isinstance(event.content, TextMessageEventContent) or not self._is_ready:
            return

        synced_room = await self._get("synced_room")
        if not synced_room or str(event.room_id) != str(synced_room):
            return

        prefixes = await mx.get_prefix()
        if isinstance(prefixes, list): prefixes = tuple(prefixes)
        my_id = mx.client.mxid if hasattr(mx.client, "mxid") else getattr(mx, "user_id", None)

        if event.content.body.startswith(prefixes): return
        if str(event.sender) != str(my_id): return
        
        # ПРОВЕРКА ЭХА: игнорируем сообщения, которые начинаются как [Имя]: 
        # (это сообщения, которые бот сам переслал из TG)
        if event.content.body.startswith("[") and "]:" in event.content.body:
            return

        if self.tg_client and await self.tg_client.is_user_authorized():
            try:
                self._last_bridged_text = event.content.body
                msg = await self.tg_client.send_message(self.tg_chat_id, event.content.body)
                await self._set("last_tg_msg_id", msg.id)
            except Exception as e:
                logger.error(f"Ошибка отправки в TG: {e}")

    def _matrix_stop(self, mx):
        if self.tg_client:
            asyncio.create_task(self.tg_client.disconnect())