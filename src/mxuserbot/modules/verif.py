#			__  ____  ___   _               _           _   
#			|  \/  \ \/ / | | |___  ___ _ __| |__   ___ | |_ 
#			| |\/| |\  /| | | / __|/ _ \ '__| '_ \ / _ \| __|
#			| |  | |/  \| |_| \__ \  __/ |  | |_) | (_) | |_ 
#			|_|  |_/_/\_\\___/|___/\___|_|  |_.__/ \___/ \__| 
#
# 🔒      Licensed under the GNU AGPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio

from mautrix.types import MessageEvent, TrustState


class Meta:
    name = "VerifierModule"
    description = "Device trust management and verification."
    version = "1.0.1"
    tags = ["settings"]




from mxc.exceptions import UsageError
from mxc import utils
from .. import loader


@loader.tds
class VerifierModule(loader.Module):
    strings = {
        "fetching": "🔍 | <b>Fetching devices...</b>",
        "no_devices": "❌ | <b>No devices found.</b>",
        "dev_list_header": "📱 | <b>Your Devices:</b><br><br>",
        "dev_bot": "🤖 <b>(This Bot)</b>",
        "dev_verified": "✅ <b>Verified</b>",
        "dev_unverified": "❌ <b>Unverified</b>",
        "dev_item": "🖥 | <b>{name}</b><br>└ <code>{id}</code> | {status}<br><br>",
        "dev_footer": "<i>Use <code>.verif [device_id]</code> to verify a specific device.</i>",
        "no_id": "❌ | <b>Please specify a Device ID. Use <code>.devices</code> to find it.</b>",
        "cant_verify_self": "❌ | <b>You cannot verify the bot itself.</b>",
        "checking": "🔍 | <b>Checking device <code>{id}</code>...</b>",
        "not_found": "❌ | <b>Device <code>{id}</code> not found in your account.</b>",
        "already_verif": "✅ | <b>Device <code>{id}</code> is already verified!</b>",
        "check_other_device": "🛡 | <b>Verification initiated for:</b> <code>{id}</code><br>⏳ <i>Please accept the request on that device.</i>",
        "waiting_emoji": "⏳ | <b>Waiting for SAS emoji from device <code>{id}</code>...</b>",
        "verif_emoji": "🔐 | <b>SAS Emoji for device <code>{id}</code>:</b><br><br><code>{emojis}</code><br><br>⏳ <i>Verification in progress...</i>",
        "verif_success": "✅ | <b>Device <code>{id}</code> verified successfully!</b>",
        "verif_cancelled": "❌ | <b>Verification cancelled</b> for device <code>{id}</code>.",
        "verif_failed": "❌ | <b>Verification failed</b> for device <code>{id}</code>.",
        "error": "❌ | <b>Error:</b> <code>{e}</code>"
    }

    @loader.command(security=loader.OWNER)
    async def devices(self, mx, event: MessageEvent):
        """Lists all active devices and their verification status."""
        status_id = await utils.answer(mx, self.strings.get("fetching"))
        
        devices_resp = await mx.client.api.request("GET", "/_matrix/client/v3/devices")
        my_devices = devices_resp.get("devices", [])
        
        msg = self.strings.get("dev_list_header")
        bot_mxid = mx.client.mxid
        bot_pub_key = mx.client.crypto.account.signing_key
        store = mx.client.crypto.crypto_store

        from mautrix.types import CrossSigner

        for dev in my_devices:
            d_id = dev['device_id']
            d_name = dev.get('display_name', 'Unknown Device')
            
            if d_id == mx.client.device_id:
                status = self.strings.get("dev_bot")
            else:
                device_info = await store.get_device(bot_mxid, d_id)

                is_verified = False
                if device_info:
                    if device_info.trust >= TrustState.VERIFIED:
                        is_verified = True
                    else:
                        target = CrossSigner(user_id=bot_mxid, key=device_info.signing_key)
                        signer = CrossSigner(user_id=bot_mxid, key=bot_pub_key)
                        is_verified = await store.is_key_signed_by(target, signer)

                status = self.strings.get("dev_verified") if is_verified else self.strings.get("dev_unverified")
            
            msg += self.strings.get("dev_item").format(name=d_name, id=d_id, status=status)
        
        await utils.answer(mx, msg + self.strings.get("dev_footer"), edit_id=status_id)


    @loader.command(security=loader.OWNER)
    async def verif(self, mx, event: MessageEvent, target_id: str = None):
        """<device_id> — Start verification for a specific device."""

        if target_id == mx.client.device_id:
            return await utils.answer(mx, self.strings.get("cant_verify_self"))

        status_id = await utils.answer(mx, self.strings.get("checking").format(id=target_id))
        
        devices_resp = await mx.client.api.request("GET", "/_matrix/client/v3/devices")
        my_devices = devices_resp.get("devices",[])
        
        target_dev = next((d for d in my_devices if d['device_id'] == target_id), None)
        
        if not target_dev:
            return await utils.answer(mx, self.strings.get("not_found").format(id=target_id), edit_id=status_id)
        
        identity = await mx.client.crypto.crypto_store.get_device(mx.client.mxid, target_id)
        if not identity:
            identity = await mx.client.crypto.get_or_fetch_device(mx.client.mxid, target_id)
            
        if identity and identity.trust >= TrustState.VERIFIED:
            return await utils.answer(mx, self.strings.get("already_verif").format(id=target_id), edit_id=status_id)

        await utils.answer(mx, self.strings.get("check_other_device").format(id=target_id), edit_id=status_id)

        try:
            emojis, txn_id, result_future = await mx.sas_verifier.start_verification(
                mx.client.mxid, target_id
            )
            emoji_str = " | ".join(e.split(":", 1)[1] for e in emojis)
            await utils.answer(mx, self.strings.get("verif_emoji").format(
                id=target_id, emojis=emoji_str
            ), edit_id=status_id)

            try:
                result = await asyncio.wait_for(result_future, timeout=120)
            except asyncio.TimeoutError:
                result = "timeout"

            if result == "success":
                await utils.answer(mx, self.strings.get("verif_success").format(id=target_id))
            elif result == "cancelled":
                await utils.answer(mx, self.strings.get("verif_cancelled").format(id=target_id))
            else:
                await utils.answer(mx, self.strings.get("verif_failed").format(id=target_id))

        except asyncio.CancelledError:
            await utils.answer(mx, self.strings.get("verif_cancelled").format(id=target_id), edit_id=status_id)
        except TimeoutError:
            await utils.answer(mx, self.strings.get("error").format(
                e="Verification timed out. The device did not respond."
            ), edit_id=status_id)
        except Exception as e:
            await utils.answer(mx, self.strings.get("error").format(e=str(e)), edit_id=status_id)