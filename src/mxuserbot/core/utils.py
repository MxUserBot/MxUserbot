import asyncio
import io
import os
from pathlib import Path
import platform
import shlex
import time
from typing import Optional, Union

from PIL import Image
import aiohttp
from loguru import logger
import psutil

from mautrix.api import Method
from mautrix.crypto.attachments import encrypt_attachment
from mautrix.types import (
    EncryptedEvent,
    EventType,
    Format,
    RoomTagInfo,
    ImageInfo,
    MediaMessageEventContent,
    MessageEvent,
    MessageType,
    RelatesTo,
    RelationType,
    TextMessageEventContent,
    ThumbnailInfo,
    MediaMessageEventContent
)
from mautrix.util.formatter import parse_html

from .types import Image


RPC_NAMESPACE = "com.ip-logger.msc4320.rpc"
COMM_DIR = Path(__file__).resolve().parents[1] / "modules" / "community"
_CRYPTO_BACKGROUND_TASKS = set()


async def fetch_room_messages(
    mx, 
    room_id: str, 
    limit: int = 100, 
    from_token: str = None, 
    direction: str = "b"
) -> dict:
    return await mx.client.api.request(
        "GET",
        f"/_matrix/client/v3/rooms/{room_id}/messages",
        query_params={
            "dir": direction,
            "limit": str(limit),
            "from": from_token or "",
        },
    )


async def decrypt_event(
    mx,
    event: MessageEvent,
    context_event: MessageEvent = None
) -> bool:
    if event.type != EventType.ROOM_ENCRYPTED:
        return True

    try:
        decrypted = await mx.client.crypto.decrypt_megolm_event(event)
        event.content = decrypted.content
        event.type = decrypted.type
        return True
    except:
        pass

    users_to_ask = {mx.client.mxid, event.sender}
    from_devices = {}
    for user_id in users_to_ask:
        devices = await mx.client.crypto.crypto_store.get_devices(user_id)
        if devices:
            from_devices[user_id] = {dev_id: dev.identity_key for dev_id, dev in devices.items()}

    if from_devices:
        task = asyncio.create_task(mx.client.crypto.request_room_key(
            room_id=event.room_id,
            sender_key=event.content.sender_key,
            session_id=event.content.session_id,
            from_devices=from_devices
        ))
        _CRYPTO_BACKGROUND_TASKS.add(task)
        task.add_done_callback(_CRYPTO_BACKGROUND_TASKS.discard)

        for _ in range(2):
            await asyncio.sleep(2)
            try:
                decrypted = await mx.client.crypto.decrypt_megolm_event(event)
                event.content = decrypted.content
                event.type = decrypted.type
                return True
            except:
                continue
    return False


async def get_reply_event(
    mx,
    event: MessageEvent
) -> Optional[MessageEvent]:
    relates = getattr(event.content, "relates_to", None) or getattr(event.content, "_relates_to", None)
    if not relates:
        return None
        
    reply_to = getattr(relates, "in_reply_to", None)
    if not reply_to or not reply_to.event_id:
        return None

    try:
        replied_event = await mx.client.get_event(event.room_id, reply_to.event_id)
        
        await decrypt_event(mx, replied_event)
        
        try:
            url = f"{mx.client.api.base_url}/_matrix/client/v1/rooms/{event.room_id}/relations/{reply_to.event_id}/m.replace"
            headers = {"Authorization": f"Bearer {mx.client.api.token}"}
            
            async with mx.client.api.session.get(url, headers=headers) as res:
                if res.status == 200:
                    data = await res.json()
                    chunks = data.get("chunk", [])
                    
                    if chunks:
                        latest_dict = max(chunks, key=lambda x: x.get("origin_server_ts", 0))
                        
                        latest_edit_event = MessageEvent.deserialize(latest_dict)

                        await decrypt_event(mx, latest_edit_event)

                        content = latest_edit_event.content
                        new_content = getattr(content, "new_content", None)
                        if not new_content and isinstance(content, dict):
                            new_content = content.get("m.new_content")

                        if new_content:
                            new_body = getattr(new_content, "body", None) or new_content.get("body")
                            if new_body:
                                replied_event.content.body = new_body
        except Exception:
            pass
            
        return replied_event
    except Exception:
        return None


async def get_reply_text(mx, event: MessageEvent) -> str | None | bool:
    """
    Extracts text from a reply with auto-decryption and key handling.
    Returns:
    - str (text) if successful
    - False if there is no reply
    - None if the key is missing or an error occurred
    """
    reply_to = getattr(event.content, "relates_to", None)
    if not reply_to or getattr(reply_to, "in_reply_to", None) is None:
        return False
        
    try:
        replied_event = await get_reply_event(mx, event)
        if not replied_event:
            raise Exception("Событие не найдено")
    except Exception as e:
        await answer(mx, text=f"❌ <b>Не удалось скачать сообщение:</b> {e}", event=event)
        return None

    return getattr(replied_event.content, "body", "")


def get_platform() -> str:
    os_info = f"{platform.system()} {platform.release()}"
    hostname = platform.node()
    ram = psutil.virtual_memory()
    
    used_ram = ram.used // 1024 // 1024
    total_ram = ram.total // 1024 // 1024
    ram_usage = f"{used_ram} / {total_ram} MB"
    
    cpu_usage = psutil.cpu_percent()

    return (
        f"<b>Сервер:</b> `{hostname}`<br>"
        f"<b>ОС:</b> `{os_info}`<br>"
        f"<b>Память:</b> `{ram_usage}`<br>"
        f"<b>Нагрузка CPU:</b> `{cpu_usage}%`"
    )


def get_commands(cls) -> dict:
    """Returns a dictionary of available commands for the given class."""
    cmds = {}
    for attr_name in dir(cls):
        method = getattr(cls, attr_name)
        if callable(method) and getattr(method, "is_command", False):
            cmds[method.command_name] = method
    return cmds


async def get_args_raw(mx, event) -> str:
    """Extracts command arguments handling both standard messages and replies (in silent mode)."""
    cmd_text = ""
    if isinstance(event, str):
        cmd_text = event
    elif hasattr(event, "content") and hasattr(event.content, "body"):
        cmd_text = event.content.body
    elif hasattr(event, "message"):
        cmd_text = event.message

    cmd_args = ""
    if cmd_text:
        cmd_text = cmd_text.strip()
        parts = cmd_text.split(maxsplit=1)
        cmd_args = parts[1].strip() if len(parts) > 1 else ""

    args_words_count = len(cmd_args.split())

    if args_words_count > 1:
        return cmd_args

    try:
        relates = getattr(event.content, "relates_to", None) or getattr(event.content, "_relates_to", None)
        if relates and getattr(relates, "in_reply_to", None):
            replied_event = await mx.client.get_event(room_id=event.room_id, event_id=relates.in_reply_to.event_id)


            reply_text = getattr(replied_event.content, "body", None)
            
            if reply_text:
                reply_text = reply_text.strip()
                if cmd_args:
                    return f"{cmd_args} {reply_text}"
                return reply_text
    except Exception:
        pass

    return cmd_args


async def pin_room(
        mx,
        room_id
) -> bool:
    try:
        await mx.client.set_room_tag(
            room_id,
            "m.favorite",
            RoomTagInfo(
                order=0.0
            )
        )
        return True
    except Exception as e:
        raise e


async def unpin_room(
        mx,
        room_id
) -> bool:
    try:
        await mx.client.remove_room_tag(
            room_id,
            "m.favorite"
        )
        return True
    except Exception as e:
        raise e


async def pin(mx, room_id: str, event_id: str, unpin: bool = False):

    try:
        try:
            current_state = await mx.client.get_state_event(room_id, EventType.ROOM_PINNED_EVENTS)
            pinned = current_state.get("pinned", []) if current_state else []
        except Exception as e:
            print(e)
            pinned = []

        if unpin:
            if event_id in pinned:
                pinned.remove(event_id)
        else:
            if event_id not in pinned:
                pinned.append(event_id)

        return await mx.client.send_state_event(
            room_id=room_id,
            event_type=EventType.ROOM_PINNED_EVENTS,
            content={"pinned": pinned},
            state_key=""
        )
    except Exception as e:
        mx.logger.error(f"Failed to pin/unpin {event_id}: {e}")
        return None


async def answer(
    mx,
    text: str = None,
    image: Image = None,
    html: bool = True,
    room_id: str = None,
    event: MessageEvent = None,
    edit_id: str | None = -1,
    **kwargs
) -> str:
    ctx_event = None
    if hasattr(mx, "_current_event"):
        try:
            ctx_event = mx._current_event.get()
        except Exception:
            pass

    target_event = event or ctx_event

    if not room_id:
        if event:
            room_id = event.room_id
        elif ctx_event:
            room_id = ctx_event.room_id

    if edit_id == -1:
        if target_event:
            if target_event.sender == mx.client.mxid:
                edit_id = target_event.event_id
            else:
                edit_id = None
        else:
            edit_id = None

    if not room_id:
        logger.error("utils.answer() called without room_id and context!")
        return ""
    ctx_event = None
    if hasattr(mx, "_current_event"):
        try:
            ctx_event = mx._current_event.get()
        except Exception: pass

    target_event = event or ctx_event
    if not room_id:
        room_id = target_event.room_id if target_event else None
    if edit_id == -1:
        edit_id = target_event.event_id if target_event and target_event.sender == mx.client.mxid else None

    if not room_id:
        logger.error("utils.answer() called without room_id and context!")
        return ""

    if image and isinstance(image.url, bytes):
        if not image.size:
            image.size = len(image.url)
            
        mxc_url = await mx.client.upload_media(
            data=image.url,
            mime_type=image.mimetype,
            filename=image.filename
        )
        image.url = mxc_url

    body_text = text or ("image.png" if image else "")
    formatted_text = text if (html and text) else None

    if not edit_id:
        if image:
            content = {
                "msgtype": "m.image",
                "body": body_text,
                "url": image.url,
                "info": image.to_info()
            }
        else:
            content = {
                "msgtype": "m.text",
                "body": await parse_html(body_text) if html else body_text,
            }
            if formatted_text:
                content["format"] = "org.matrix.custom.html"
                content["formatted_body"] = formatted_text
    else:
        content = {
            "msgtype": "m.text",
            "body": f" * {body_text}",
            "m.relates_to": {
                "rel_type": "m.replace",
                "event_id": edit_id
            }
        }
        
        if image:
            content["m.new_content"] = {
                "msgtype": "m.image",
                "body": body_text,
                "url": image.url,
                "info": image.to_info()
            }
        else:
            new_content = {
                "msgtype": "m.text",
                "body": body_text,
            }
            if formatted_text:
                new_content["format"] = "org.matrix.custom.html"
                new_content["formatted_body"] = formatted_text
            content["m.new_content"] = new_content

    res = await mx.client.send_message_event(
        room_id=room_id,
        event_type=EventType.ROOM_MESSAGE,
        content=content,
        txn_id=kwargs.get("txn_id")
    )
    
    return edit_id if edit_id else res


async def request(
    url: str, 
    method: str = "GET", 
    return_type: str = "json",
    **kwargs
):
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, **kwargs) as response:
            response.raise_for_status() 
            
            if return_type == "json":
                return await response.json(content_type=None)
            elif return_type == "text":
                return await response.text()
            elif return_type == "bytes":
                return await response.read()
            return response


async def send_image(
    mx,
    room_id,
    file_bytes: bytes | None = None,
    url: str | None = None,
    file_name: str = "image.png",
    caption: str | None = None,
    info: ImageInfo | None = None,
    html: bool = True,
    **kwargs
):
    """Адекватная отправка изображений: E2EE + Thumbnail + Caption"""
    if not isinstance(room_id, str):
        room_id = room_id.room_id

    if not file_bytes and url:
        if url.startswith("http"):
            file_bytes = await request(url, return_type="bytes")
        elif url.startswith("mxc://"):
            file_bytes = await mx.client.download_media(url)
    
    if not file_bytes:
        raise ValueError("send_image: No bytes provided")

    img_obj = Image.open(io.BytesIO(file_bytes))
    w, h = img_obj.size
    
    thumb_bytes = None
    try:
        thumb_img = img_obj.copy()
        thumb_img.thumbnail((400, 400))
        t_io = io.BytesIO()
        thumb_img.save(t_io, format="PNG")
        thumb_bytes = t_io.getvalue()
        tw, th = thumb_img.size
    except: pass

    is_enc = await mx.client.state_store.is_encrypted(room_id) if mx.client.crypto else False
    
    if not info:
        info = ImageInfo(mimetype="image/png", size=len(file_bytes), width=w, height=h)

    content = MediaMessageEventContent(
        msgtype=MessageType.IMAGE,
        body=caption or file_name,
        info=info
    )

    if caption and html:
        content.format = Format.HTML
        content.formatted_body = caption

    if is_enc:
        await mx.client.crypto.wait_group_session_share(room_id)

        if thumb_bytes:
            et, ti = encrypt_attachment(thumb_bytes)
            ti.url = await mx.client.upload_media(et, mime_type="application/octet-stream")
            content.info.thumbnail_file = ti
            content.info.thumbnail_info = ThumbnailInfo(
                mimetype="image/png", size=len(thumb_bytes), width=tw, height=th
            )

        ed, fi = encrypt_attachment(file_bytes)
        fi.url = await mx.client.upload_media(ed, mime_type="application/octet-stream", filename=file_name)
        
        content.file = fi
        content.url = None
    else:
        if thumb_bytes:
            thumb_url = await mx.client.upload_media(thumb_bytes, mime_type="image/png")
            content.info.thumbnail_url = thumb_url
            content.info.thumbnail_info = ThumbnailInfo(mimetype="image/png", size=len(thumb_bytes), width=tw, height=th)
        
        content.url = await mx.client.upload_media(file_bytes, mime_type="application/octet-stream", filename=file_name)

    if "relates_to" in kwargs:
        content.relates_to = kwargs.pop("relates_to")

    return await mx.client.send_message_event(room_id, EventType.ROOM_MESSAGE, content, **kwargs)


async def set_rpc_media(
    mx,
    artist: str,
    album: str,
    track: str,
    length: Optional[int] = None,
    complete: Optional[int] = None,
    cover_art: Optional[Union[str, bytes]] = None,
    player: Optional[str] = None,
    streaming_link: Optional[str] = None
):
    """
    Set the 'Listening' status (m.rpc.media).
    If cover_art is a URL or bytes, it will be automatically uploaded to Matrix.
    """
    if cover_art:
        if isinstance(cover_art, bytes):
            mxc = await mx.client.upload_media(cover_art)
            cover_art = str(mxc)
            
        elif isinstance(cover_art, str) and cover_art.startswith(("http://", "https://")):
            img_bytes = await request(cover_art, return_type="bytes")
            if img_bytes:
                mxc = await mx.client.upload_media(img_bytes)
                cover_art = str(mxc)
            else:
                cover_art = None
                
    data = {
        "type": f"{RPC_NAMESPACE}.media",
        "artist": artist,
        "album": album,
        "track": track
    }

    if length is not None or complete is not None:
        data["progress"] = {}
        if length is not None:
            data["progress"]["length"] = length
        if complete is not None:
            data["progress"]["complete"] = complete
    
    if cover_art: 
        data["cover_art"] = cover_art
        
    if player: 
        data["player"] = player
        
    if streaming_link: 
        data["streaming_link"] = streaming_link

    endpoint = f"_matrix/client/v3/profile/{mx.client.mxid}/{RPC_NAMESPACE}"
    return await mx.client.api.request(Method.PUT, endpoint, content={RPC_NAMESPACE: data})


async def set_rpc_activity(
    mx,
    name: str,
    details: Optional[str] = None,
    image: Optional[str] = None
):
    """
    Set the 'Playing/Activity' status (m.rpc.activity).
    """
    data = {
        "type": f"{RPC_NAMESPACE}.activity",
        "name": name
    }

    if details:
        data["details"] = details
    if image:
        data["image"] = image

    endpoint = f"_matrix/client/v3/profile/{mx.client.mxid}/{RPC_NAMESPACE}"
    return await mx.client.api.request(Method.PUT, endpoint, content={RPC_NAMESPACE: data})


async def clear_rpc(mx):
    """Removes the Rich Presence status completely according to the specification."""
    endpoint = f"_matrix/client/v3/profile/{mx.client.mxid}/{RPC_NAMESPACE}"
    return await mx.client.api.request(Method.DELETE, endpoint)


async def get_args(mx, event) -> list:
    raw = await get_args_raw(mx, event)
    
    if not raw:
        return []

    try:
        args = shlex.split(raw)
    except ValueError:
        args = raw.split()

    return list(filter(lambda x: len(x) > 0, args))


def escape_html(text: str, /) -> str:
    """Escape specific HTML characters in a string to avoid injection."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_quotes(text: str, /) -> str:
    """Escape quotes to their corresponding HTML entities."""
    return escape_html(text).replace('"', "&quot;")


def get_base_dir() -> str:
    """Get the absolute directory path of the current file."""
    return get_dir(__file__)


def get_dir(mod: str) -> str:
    """Get the absolute directory path of a given module."""
    return os.path.abspath(os.path.dirname(os.path.abspath(mod)))


async def is_dm(mx, room_id: str) -> bool:
    direct_data = await mx.client.get_account_data(EventType.DIRECT)

    return any(
        room_id in rooms
        for rooms in direct_data.values()
    )


def _get_safe_path(filename: str) -> Path:
    safe_name = os.path.basename(filename)
    final_path = (COMM_DIR / safe_name).resolve()

    if COMM_DIR not in final_path.parents and final_path != COMM_DIR:
        raise PermissionError("Security: Access restricted to community folder only.")

    forbidden_ext = {".py", ".pyc", ".sh", ".bash", ".exe", ".so", ".dll"}
    if final_path.suffix.lower() in forbidden_ext:
        raise PermissionError(f"Security: Prohibited file extension: {final_path.suffix}")

    return final_path


async def safe_save(file_bytes: bytes, filename: str) -> str:
    path = _get_safe_path(filename)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return str(path)


async def safe_remove(filename: str):
    path = _get_safe_path(filename)
    if path.exists():
        os.remove(path)
