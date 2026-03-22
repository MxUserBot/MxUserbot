#!/usr/bin/env python3

import asyncio
import functools
import glob
import importlib
import json

import yaml
import os
import re
import signal
import sys
import traceback
import urllib.parse
import logging
import logging.config
import datetime
import hashlib
from importlib import reload
from io import BytesIO
# from PIL import Image

import requests
from nio import AsyncClient, InviteEvent, JoinError, RoomMessageText, MatrixRoom, LoginError, RoomMemberEvent, \
    RoomVisibility, RoomPreset, RoomCreateError, RoomResolveAliasResponse, UploadError, UploadResponse, SyncError, \
    RoomPutStateError


from .modules.core.load_settings import load_settings 
from .modules.core.room_send import room_send
from .modules.core.send_text import send_text
from .modules.core.account_settings import is_owner
from .modules.core.account_settings import set_account_data
from .modules.core.load_modues import load_module
from .modules.core.account_settings import get_account_data


from .modules.core.exceptions import CommandRequiresAdmin, CommandRequiresOwner, UploadFailed, handle_error_response
from .registry import active_modules

class Bot:

    def __init__(self):

        self.client = None
        
        self.modules = active_modules
        self.version = "1"
        self.info = "хуйлан"


        self.uri_cache = dict()

        

        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.logger = None



        self.initialize_logger()

    def initialize_logger(self):

        if os.path.exists('config/logging.yml'):
            with open('config/logging.yml') as f:
                config = yaml.load(f, Loader=yaml.Loader)
                logging.config.dictConfig(config)
        else:
            log_format = '%(levelname)s - %(name)s - %(message)s'
            logging.basicConfig(format=log_format)

        self.logger = logging.getLogger("hemppa")

        if self.debug:
            logging.root.setLevel(logging.DEBUG)
            self.logger.info("enabled debugging")

        self.logger.debug("Logger initialized")

    def get_uri_cache(self, url, blob=False):
        """

        :param url: Url of binary content of the image to upload
        :param blob: Flag to indicate if the second param is an url or a binary content
        :return: [matrix_uri, mimetype, w, h, size], or None
        """
        cache_key = url
        if blob:  ## url is bytes, cannot be used a key for cache
            cache_key = hashlib.md5(url).hexdigest()

        return self.uri_cache.get(cache_key)


    # async def upload_and_send_image(self, room, url, event=None, text=None, blob=False, blob_content_type="image/png", no_cache=False):
    #     """

    #     :param room: A MatrixRoom the image should be send to after uploading
    #     :param url: Url of binary content of the image to upload
    #     :param text: A textual representation of the image
    #     :param blob: Flag to indicate if the second param is an url or a binary content
    #     :param blob_content_type: Content type of the image in case of binary content
    #     :param no_cache: Set to true if you want to bypass cache and always re-upload the file
    #     :return:
    #     """

    #     if not text and not blob:
    #         text = f"Image: {url}"

    #     res = self.get_uri_cache(url, blob=blob)
    #     if res:
    #         try:
    #             matrix_uri, mimetype, w, h, size = res
    #             return await self.send_image(room, matrix_uri, text, event, mimetype, w, h, size)
    #         except ValueError: # broken cache?
    #             self.logger.warning(f"Image cache for {url} could not be unpacked, attempting to re-upload...")
    #     try:
    #         matrix_uri, mimetype, w, h, size = await self.upload_image(url, blob=blob, no_cache=no_cache)
    #     except (UploadFailed, ValueError):
    #         return await self.send_text(room, f"Sorry. Something went wrong fetching {url} and uploading the image to matrix server :(", event=event)

    #     return await self.send_image(room, matrix_uri, text, event, mimetype, w, h, size)



    # Helper function to upload a image from URL to homeserver. Use send_image() to actually send it to room.
    # Throws exception if upload fails
    # async def upload_image(self, url_or_bytes, blob=False, blob_content_type="image/png", no_cache=False):
    #     """
    #     :param url_or_bytes: Url or binary content of the image to upload
    #     :param blob: Flag to indicate if the first param is an url or a binary content
    #     :param blob_content_type: Content type of the image in case of binary content
    #     :param no_cache: Flag to indicate whether to cache the resulting uploaded details
    #     :return: A MXC-Uri https://matrix.org/docs/spec/client_server/r0.6.0#mxc-uri, Content type, Width, Height, Image size in bytes
    #     """

    #     self.client: AsyncClient
    #     response: UploadResponse

    #     cache_key = url_or_bytes
    #     if blob:  ## url is bytes, cannot be used a key for cache
    #         cache_key = hashlib.md5(url_or_bytes).hexdigest()

    #     if no_cache:
    #         cache_key = None

    #     if blob:
    #         i = Image.open(BytesIO(url_or_bytes))
    #         image_length = len(url_or_bytes)
    #         content_type = blob_content_type
    #         (response, alist) = await self.client.upload(lambda a, b: url_or_bytes, blob_content_type, filesize=image_length)
    #     else:
    #         self.logger.debug(f"start downloading image from url {url_or_bytes}")
    #         headers = {'User-Agent': 'Mozilla/5.0'}
    #         url_response = requests.get(url_or_bytes, headers=headers)
    #         self.logger.debug(f"response [status_code={url_response.status_code}, headers={url_response.headers}")

    #         if url_response.status_code == 200:
    #             content_type = url_response.headers.get("content-type")
    #             self.logger.info(f"uploading content to matrix server [size={len(url_response.content)}, content-type: {content_type}]")
    #             (response, alist) = await self.client.upload(lambda a, b: url_response.content, content_type)
    #             self.logger.debug("response: %s", response)
    #             i = Image.open(BytesIO(url_response.content))
    #             image_length = len(url_response.content)
    #         else:
    #             self.logger.error("unable to request url: %s", url_response)
    #             raise UploadFailed

        # if isinstance(response, UploadResponse):
        #     self.logger.info("uploaded file to %s", response.content_uri)
        #     res = [response.content_uri, content_type, i.size[0], i.size[1], image_length]
        #     if cache_key:
        #         self.uri_cache[cache_key] = res
        #     return res
        # else:
        #     response: UploadError
        #     self.logger.error("unable to upload file. msg: %s", response.message)

        # raise UploadFailed



    async def send_html(self, room, html, plaintext, event=None, msgtype="m.notice", bot_ignore=False):
        """

        :param room: A MatrixRoom the html should be send to
        :param html: Html content of the message
        :param plaintext: Plaintext content of the message
        :param msgtype: The message type for the room https://matrix.org/docs/spec/client_server/latest#m-room-message-msgtypes
        :param bot_ignore: Flag to mark the message to be ignored by the bot
        :return:
        """

        msg = {
            "msgtype": msgtype,
            "format": "org.matrix.custom.html",
            "formatted_body": html,
            "body": plaintext
        }
        if bot_ignore:
            msg["org.vranki.hemppa.ignore"] = "true"
        await room_send(room.room_id, event, 'm.room.message', msg)

    async def send_location(self, room, body, latitude, longitude, event=None, bot_ignore=False, asset='m.pin'):
        """

        :param room: A MatrixRoom the html should be send to
        :param html: Html content of the message
        :param body: Plaintext content of the message
        :param latitude: Latitude in WGS84 coordinates (float)
        :param longitude: Longitude in WGS84 coordinates (float)
        :param bot_ignore: Flag to mark the message to be ignored by the bot
        :param asset: Asset string as defined in MSC3488 (such as m.self or m.pin)
        :return:
        """
        locationmsg = {
            "body": str(body),
            "geo_uri": 'geo:' + str(latitude) + ',' + str(longitude),
            "msgtype": "m.location",
            "org.matrix.msc3488.asset": { "type": asset }
            }
        await room_send(room.room_id, event, 'm.room.message', locationmsg)

    async def send_image(self, room, url, body, event=None, mimetype=None, width=None, height=None, size=None):
        """

        :param room: A MatrixRoom the image should be send to
        :param url: A MXC-Uri https://matrix.org/docs/spec/client_server/r0.6.0#mxc-uri
        :param body: A textual representation of the image
        :param mimetype: The mimetype of the image
        :param width: Width in pixel of the image
        :param height: Height in pixel of the image
        :param size: Size in bytes of the image
        :return:
        """
        msg = {
            "url": url,
            "body": body,
            "msgtype": "m.image",
            "info": {
                "thumbnail_info": None,
                "thumbnail_url": url,
            },
        }

        if mimetype:
            msg["info"]["mimetype"] = mimetype
        if width:
            msg["info"]["w"] = width
        if height:
            msg["info"]["h"] = height
        if size:
            msg["info"]["size"] = size

        self.logger.debug(f"send image room message: {msg}")

        return await room_send(room.room_id, event, 'm.room.message', msg)

    async def set_room_avatar(self, room, uri):
        """

        :param room: A MatrixRoom the image should be send as room avatar event
        :param uri: A MXC-Uri https://matrix.org/docs/spec/client_server/r0.6.0#mxc-uri
        :return:
        """
        msg = {
            "url": uri
        }

        result = await self.client.room_put_state(room.room_id, 'm.room.avatar', msg)

        if isinstance(result, RoomPutStateError):
            self.logger.warning(f"can't set room avatar. {result.message}")
            await send_text(self, room, f"sorry. can't set room avatar. I need at least be a moderator")

        return result

    async def send_msg(self, mxid, roomname, message):
        """

        :param mxid: A Matrix user id to send the message to
        :param roomname: A Matrix room id to send the message to
        :param message: Text to be sent as message
        :return bool: Success upon sending the message
        """
        # Sends private message to user. Returns true on success.
        msg_room = await self.find_or_create_private_msg(mxid, roomname)
        if not msg_room or (type(msg_room) is RoomCreateError):
            self.logger.error(f'Unable to create room when trying to message {mxid}')
            return False

        # Send message to the room
        await send_text(self, msg_room, message)
        return True

    async def find_or_create_private_msg(self, mxid, roomname):
        # Find if we already have a common room with user:
        msg_room = None
        for croomid in self.client.rooms:
            roomobj = self.client.rooms[croomid]
            if len(roomobj.users) == 2:
                for user in roomobj.users:
                    if user == mxid:
                        msg_room = roomobj

        # Nope, let's create one
        if not msg_room:
            msg_room = await self.client.room_create(visibility=RoomVisibility.private,
                name=roomname,
                is_direct=True,
                preset=RoomPreset.private_chat,
                invite={mxid},
            )
        return msg_room


    def remove_callback(self, callback):
        for cb_object in self.client.event_callbacks:
            if cb_object.func == callback:
                self.logger.info("remove callback")
                self.client.event_callbacks.remove(cb_object)

    def get_room_by_id(self, room_id):
        try:
            return self.client.rooms[room_id]
        except KeyError:
            return None

    async def get_room_by_alias(self, alias):
        rar = await self.client.room_resolve_alias(alias)
        if type(rar) is RoomResolveAliasResponse:
            return rar.room_id
        return None

    # Throws exception if event sender is not a room admin
    def must_be_admin(self, room, event, power_level=50):
        if not self.is_admin(room, event, power_level=power_level):
            raise CommandRequiresAdmin

    # Throws exception if event sender is not a bot owner
    def must_be_owner(self, event):
        if not is_owner(event):
            raise CommandRequiresOwner

    # Returns true if event's sender has PL50 or more in the room event was sent in,
    # or is bot owner
    def is_admin(self, room, event, power_level=50):
        if is_owner(event):
            return True
        if event.sender not in room.power_levels.users:
            return False
        return room.power_levels.users[event.sender] >= power_level



    # Checks if this event should be ignored by bot, including custom property
    def should_ignore_event(self, event):
        return "org.vranki.hemppa.ignore" in event.source['content']




    def reload_modules(self):
        for modulename in self.modules:
            self.logger.info(f'Reloading {modulename} ..')
            self.modules[modulename] = load_module(modulename)

            load_settings(get_account_data())



    def clear_modules(self):
        self.modules = dict()
