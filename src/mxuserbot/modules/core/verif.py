from ...core import utils, loader
from mautrix.types import MessageEvent, TrustState

class Meta:
    name = "VerifierModule"
    _cls_doc = "Device trust management and verification."
    version = "1.0.1"
    tags = ["settings"]
    
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
        "initiated": "🛡 | <b>Verification initiated for:</b> <code>{id}</code><br>⏳ <i>Please accept the request on that device.</i>",
        "error": "❌ | <b>Error:</b> <code>{e}</code>"
    }

    @loader.command()
    async def devices(self, mx, event: MessageEvent):
        """Lists all active devices and their verification status."""
        await utils.answer(mx, self.strings.get("fetching"))
        
        try:
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

                    print(device_info)
                    
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
            
            await utils.answer(mx, msg + self.strings.get("dev_footer"))
        except Exception as e:
            await utils.answer(mx, self.strings.get("error").format(e=str(e)))


    @loader.command()
    async def verif(self, mx, event: MessageEvent):
        """<device_id> — Start verification for a specific device."""
        args = await utils.get_args(mx, event)
        
        if not args:
            return await utils.answer(mx, self.strings.get("no_id"))
            
        target_id = args[0]
        
        if target_id == mx.client.device_id:
            return await utils.answer(mx, self.strings.get("cant_verify_self"))
            
        await utils.answer(mx, self.strings.get("checking").format(id=target_id))
        
        try:
            devices_resp = await mx.client.api.request("GET", "/_matrix/client/v3/devices")
            my_devices = devices_resp.get("devices",[])
            
            target_dev = next((d for d in my_devices if d['device_id'] == target_id), None)
            
            if not target_dev:
                return await utils.answer(mx, self.strings.get("not_found").format(id=target_id))
            
            identity = await mx.client.crypto.crypto_store.get_device(mx.client.mxid, target_id)
            if not identity:
                identity = await mx.client.crypto.get_or_fetch_device(mx.client.mxid, target_id)
                
            if identity and identity.trust >= TrustState.VERIFIED:
                return await utils.answer(mx, self.strings.get("already_verif").format(id=target_id))
                
            await mx.sas_verifier.start_verification(mx.client.mxid, target_id, event.room_id)
            await utils.answer(mx, self.strings.get("initiated").format(id=target_id))
            
        except Exception as e:
            await utils.answer(mx, self.strings.get("error").format(e=str(e)))