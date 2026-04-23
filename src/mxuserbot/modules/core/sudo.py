import time
from ...core import loader, utils

class Meta:
    name = "Security"
    description = "Ultimate access control with validation."
    version = "1.0.0"
    tags = ["settings"]


@loader.tds
class SecurityModule(loader.Module):
    
    strings = {
        "name": "Security",
        "modaccess_usage": "<b>Usage:</b> <code>.modaccess add/rm @user:id PingPongModule/ping</code>",
        "not_found": "❌ Entity <code>{}</code> (as class or command) not found!",
        "mod_opened": "🔓 Access to the <b>entire module</b> <code>{}</code> granted for <code>{}</code>",
        "cmd_opened": "🔓 Access to the <b>command</b> <code>{}</code> granted for <code>{}</code>",
        "access_closed": "🔒 Access to <code>{}</code> revoked for <code>{}</code>",
        "invalid_action": "❌ Use <code>add</code> or <code>rm</code>",
        "sudo_usage": "<b>Usage:</b> <code>.sudo add/rm @user:id</code>",
        "sudo_added": "👤 User <code>{}</code> is now <b>SUDO</b>.",
        "sudo_removed": "👤 User <code>{}</code> is no longer <b>SUDO</b>.",
        "tsec_usage": "<b>Usage:</b> <code>.tsec @user:id ping 10</code>",
        "cmd_not_exist": "❌ Command <code>{}</code> does not exist!",
        "invalid_mins": "❌ Minutes must be an integer!",
        "tsec_granted": "⏱ <code>{}</code> now has {} min. for command <code>{}</code>"
    }


    @loader.command(security=loader.OWNER)
    async def modaccess(self, mx, event):
        """<add/rm> <@user:id> <name> | Module (Class) or command access"""
        args = await utils.get_args(mx, event)
        if len(args) < 3:
            return await utils.answer(mx, self.strings.get("modaccess_usage"))
        
        action, target, target_name = args[0].lower(), args[1], args[2].lower()
        
        is_mod = False
        is_cmd = False
        
        for mod in mx.active_modules.values():
            if mod.__class__.__name__.lower() == target_name:
                is_mod = True
            
            if hasattr(mod, "commands") and target_name in mod.commands:
                is_cmd = True

        if not is_mod and not is_cmd:
            return await utils.answer(
                mx, 
                self.strings.get("not_found").format(target_name)
            )

        security = mx._bot.security
        perms = security.mod_perms
        if target not in perms: 
            perms[target] = []

        if action == "add":
            if target_name not in perms[target]: 
                perms[target].append(target_name)
            
            if is_mod:
                msg = self.strings.get("mod_opened").format(target_name, target)
            else:
                msg = self.strings.get("cmd_opened").format(target_name, target)
                
        elif action == "rm":
            if target_name in perms[target]: 
                perms[target].remove(target_name)
            msg = self.strings.get("access_closed").format(target_name, target)
        else:
            return await utils.answer(mx, self.strings.get("invalid_action"))

        await mx._bot._db.set("core", "mod_perms", perms)
        await utils.answer(mx, msg)


    @loader.command(security=loader.OWNER)
    async def sudo(self, mx, event):
        """<add/rm> <@user:id> | Manage SUDO users"""
        args = await utils.get_args(mx, event)
        if len(args) < 2:
            return await utils.answer(mx, self.strings.get("sudo_usage"))
        
        action, target = args[0].lower(), args[1]
        security = mx._bot.security 

        if action == "add":
            security.sudos.add(target)
            msg = self.strings.get("sudo_added").format(target)
        elif action == "rm":
            security.sudos.discard(target)
            msg = self.strings.get("sudo_removed").format(target)
        else:
            return await utils.answer(mx, self.strings.get("invalid_action"))
            
        await mx._bot._db.set("core", "sudos", list(security.sudos))
        await utils.answer(mx, msg)


    @loader.command(security=loader.OWNER)
    async def tsec(self, mx, event):
        """<@user:id> <cmd> <min> | Temporary permissions"""
        args = await utils.get_args(mx, event)
        if len(args) < 3:
            return await utils.answer(mx, self.strings.get("tsec_usage"))
        
        target, cmd, mins = args[0], args[1].lower(), args[2]
        
        cmd_exists = any(cmd in m.commands for m in mx.active_modules.values())
        if not cmd_exists:
            return await utils.answer(
                mx, 
                self.strings.get("cmd_not_exist").format(cmd)
            )

        try:
            exp = time.time() + (int(mins) * 60)
        except ValueError:
            return await utils.answer(mx, self.strings.get("invalid_mins"))

        security = mx._bot.security
        security.tsec_users.append({"target": target, "command": cmd, "expires": exp})
        
        await mx._bot._db.set("core", "tsec_users", security.tsec_users)
        
        await utils.answer(
            mx, 
            self.strings.get("tsec_granted").format(target, mins, cmd)
        )