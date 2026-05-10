#			__  ____  ___   _               _           _   
#			|  \/  \ \/ / | | |___  ___ _ __| |__   ___ | |_ 
#			| |\/| |\  /| | | / __|/ _ \ '__| '_ \ / _ \| __|
#			| |  | |/  \| |_| \__ \  __/ |  | |_) | (_) | |_ 
#			|_|  |_/_/\_\\___/|___/\___|_|  |_.__/ \___/ \__| 
#
# 🔒      Licensed under the GNU AGPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html


class Meta:
    name = "LoaderModule"
    description = "Module Manager"
    version = "3.0.0"
    tags = ["system"]


import logging
from pathlib import Path
from typing import Any

from mautrix.types import MessageEvent
from pydantic import BaseModel, ConfigDict, Field, model_validator


from mxc.exceptions import UsageError
from mxc import utils
from .. import loader


class MdlPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    target: str = ""
    is_dev: bool = False

    @model_validator(mode='before')
    @classmethod
    def parse_mdl(cls, v: Any):
        if not v or not isinstance(v, str):
            return {"target": ""}
        parts = v.split(maxsplit=1)
        if parts[0].lower() == "dev":
            return {"is_dev": True, "target": parts[1] if len(parts) > 1 else ""}
        return {"is_dev": False, "target": v}

class RepoPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    url: str

    @model_validator(mode='before')
    @classmethod
    def parse(cls, v: Any):
        if isinstance(v, str):
            return {"url": utils.convert_repo_url(v.strip())}
        return {"url": ""}

class SearchPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    query: str = Field(default="")

    @model_validator(mode='before')
    @classmethod
    def parse_search(cls, v: Any):
        return {"query": v.strip()} if isinstance(v, str) else {"query": ""}

class UnmdPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str

    @model_validator(mode='before')
    @classmethod
    def parse(cls, v: Any):
        return {"name": v.strip()} if isinstance(v, str) else {"name": ""}



@loader.tds
class LoaderModule(loader.Module):
    config = {
        "repo_url": loader.ConfigValue("https://raw.githubusercontent.com/MxUserBot/mx-modules/main", "Main system repository URL"),
        "repo_warn_ok": loader.ConfigValue(False, "User accepted third-party repo warning"),
        "dev_warn_ok": loader.ConfigValue(False, "User accepted dev/file installation warning")
    }

    strings = {
        "downloading": "⏳ | <b>Downloading...</b>",
        "fetching": "⏳ | <b>Processing <code>{id}</code>...</b>",
        "repo_not_found": "❌ | <b>Module <code>{id}</code> not found in any repository.</b>",
        "search_empty": "❌ | <b>No modules found for query: <code>{query}</code>.</b>",
        "done": "✅ | <b>Module <code>{name}</code> loaded successfully!</b>",
        "error": "❌ | <b>Error: <code>{err}</code></b>",
        "reloading": "⏳ | <b>Reloading all modules...</b>",
        "reloaded": "♻️ | <b>Modules reloaded. Total: {count}</b>",
        "unloaded": "✅ | <b>Module <code>{name}</code> unloaded.</b>",
        "search_header": "<b>{icon} | Found in {type} Repo: <code>{url}</code></b><br>",
        "search_item": "📦 | <b>{name}</b> (<code>{id}</code>) v<b>{version}</b><br>📥 | <b><code>.mdl {cmd_id}</code></b><br>",
        "confirm_unsafe": "⚠️ | <b>SECURITY WARNING</b><br>You are installing a module from <b>{source}</b> — an <b>UNVERIFIED</b> source.<br>This module has <b>NOT</b> been reviewed and may contain malicious code.<br><br><b>Do you confirm that you want to install this module?</b>",
        "confirm_cancelled": "❌ | <b>Installation cancelled by user.</b>",
        "dev_usage": "❌ | <b>Direct links/files require <code>dev</code> prefix.</b>",
        "no_args": "❌ | <b>Provide Module ID, URL or reply to a .py file!</b>",
        "repo_added": "✅ | <b>Repository added: <code>{url}</code></b>",
        "repo_removed": "✅ | <b>Repository removed.</b>",
        "invalid_file": "❌ | <b>ONLY .PY AND .ZIP FILES ACCEPTED!</b>"
    }

    async def _matrix_start(self, mx):
        self.repo = loader.RepoManager(mx, self._db, self.config.get("repo_url"))

    async def _security_gate(self, mx, event, payload: MdlPayload, source_verified: bool, is_file: bool = False, on_confirm=None):
        is_direct = payload.target.startswith(("http", "import ", "from ")) or is_file

        if is_direct and not payload.is_dev:
            raise UsageError(self.strings["dev_usage"])

        if is_direct:
            return await self._confirm_unsafe(mx, event, "dev", on_confirm=on_confirm)
        elif not source_verified:
            return await self._confirm_unsafe(mx, event, "repo", on_confirm=on_confirm)

        return True

    async def _confirm_unsafe(self, mx, event, warn_type, on_confirm=None):
        conf_key = f"{warn_type}_warn_ok"
        if self.config.get(conf_key):
            return True

        source_name = "community repository" if warn_type == "repo" else "direct link/file"

        async def _callback(ctx):
            if ctx.payload == "yes":
                self.config.set(conf_key, True)
                if on_confirm:
                    await on_confirm(ctx)
            else:
                await ctx.edit(self.strings["confirm_cancelled"])
            await ctx.close(clear_reactions=True)

        markup = utils.EmojiKeyBoard(
            rows=[[
                utils.EmojiButton("✅", "yes"),
                utils.EmojiButton("❌", "no"),
            ]],
            callback=_callback,
            allowed_senders=event.sender,
            single_use=True,
        )

        await utils.answer(
            mx,
            self.strings["confirm_unsafe"].format(source=source_name),
            event=event,
            reply_markup=markup,
        )
        return False


    @loader.command(aliases=["ms"], security=loader.OWNER)
    async def msearch(self, mx, event: MessageEvent, payload: SearchPayload):
        """<query> — search module in repo"""
        if not payload.query:
            raise UsageError
        results = await self.repo.search(payload.query)
        if not results:
            return await utils.answer(mx, self.strings["search_empty"].format(query=payload.query))

        items = []
        for res in results:
            icon, rtype = ("✅", "SYSTEM") if res["is_verified"] else ("👥", "COMMUNITY")
            header = self.strings["search_header"].format(icon=icon, type=rtype, url=res["repo_url"])
            
            prefix = ""
            if not res["is_verified"]:
                parts = res["repo_url"].split("/")
                prefix = f"{parts[3]}/" if "github" in res["repo_url"] and len(parts) > 3 else "comm/"

            mods = [
                self.strings["search_item"].format(
                    name=mod.get("name", "Unknown"),
                    id=mod.get("id"),
                    version=mod.get("version", "1.0.0"),
                    cmd_id=f"{prefix}{mod.get('id')}"
                ) for mod in res["modules"]
            ]
            items.append(header + "".join(mods))

        total_mods = sum(len(res["modules"]) for res in results)
        if total_mods <= 3:
            await utils.answer(mx, "<br>".join(items))
            return

        per_page = 3
        pages = []
        acc = []
        count = 0
        for item in items:
            acc.append(item)
            count += 1
            if count >= per_page:
                pages.append("<br>".join(acc))
                acc = []
                count = 0
        if acc:
            pages.append("<br>".join(acc))

        async def on_page(ctx):
            page = ctx.data["page"]
            if ctx.payload == "prev":
                page = max(0, page - 1)
            elif ctx.payload == "next":
                page = min(len(pages) - 1, page + 1)
            ctx.data["page"] = page
            await ctx.edit(pages[page])

        markup = utils.EmojiKeyBoard(
            rows=[[
                utils.EmojiButton(emoji="⬅️", data="prev"),
                utils.EmojiButton(emoji="➡️", data="next"),
            ]],
            callback=on_page,
            data={"page": 0},
            allowed_senders=event.sender,
            remove_clicked=False,
        )
        await utils.answer(mx, pages[0], event=event, reply_markup=markup)

    async def _show_module_help(self, mx, event, filename: str):
        from pathlib import Path
        stem = Path(filename).stem
        mod = mx.active_modules.get(stem)
        if not mod:
            return
        prefix = await utils.get_prefix(mx)
        name = getattr(getattr(mod, "Meta", None), "name", stem)
        desc = getattr(getattr(mod, "Meta", None), "description", "")
        commands = getattr(mod, "commands", {})
        lines = [f"<b>📦 | {name}</b><br><i>{desc}</i><br>"]
        if commands:
            lines.append("<br><b>🛠 | Commands:</b><br>")
            for cmd_name, func in commands.items():
                doc = func.__doc__ or "No description"
                lines.append(f" • <code>{prefix}{cmd_name}</code> — <i>{doc}</i><br>")
        await utils.answer(mx, "".join(lines), event=event)


    @loader.command(security=loader.OWNER)
    async def mdl(self, mx, event: MessageEvent, payload: MdlPayload):
        """[dev] <id/url/reply> — install module."""
        reply_event = await utils.get_reply_event(mx, event)

        if reply_event:
            fname, content = await self.repo.get_file_content(reply_event)

            if not fname.endswith((".py", ".zip")):
                raise UsageError(self.strings["invalid_file"])

            install_kw = {"filename": fname}
            if fname.endswith(".zip"):
                install_kw["code"] = content
            else:
                install_kw["code"] = content.decode("utf-8", errors="ignore")

            status_id = await utils.answer(mx, self.strings["downloading"])

            async def _install(ctx):
                await ctx.close(clear_reactions=True)
                if await self.repo.install(**install_kw):
                    await utils.answer(mx, self.strings["done"].format(name=fname), edit_id=status_id)
                    await self._show_module_help(mx, event, fname)
                else:
                    await utils.answer(mx, self.strings["error"].format(err="Install failed!"), edit_id=status_id)

            if not await self._security_gate(mx, event, payload, False, is_file=True, on_confirm=_install):
                return

            if await self.repo.install(**install_kw):
                await utils.answer(mx, self.strings["done"].format(name=fname), edit_id=status_id)
                await self._show_module_help(mx, event, fname)
            else:
                raise ValueError("Installation failed")
            return

        if not payload.target:
            raise UsageError(self.strings["no_args"])

        status_id = await utils.answer(mx, self.strings["fetching"].format(id=payload.target[:20]))
        url, source = await self.repo.resolve_and_download(payload.target)

        if not url:
            return await utils.answer(mx, self.strings["repo_not_found"].format(id=payload.target), edit_id=status_id)

        async def _install(ctx):
            await ctx.close(clear_reactions=True)
            await utils.answer(mx, self.strings["downloading"], edit_id=status_id)
            if await self.repo.install(target=payload.target):
                filename = url.split("/")[-1]
                if not filename.endswith((".py", ".zip")): filename += ".py"
                await utils.answer(mx, self.strings["done"].format(name=filename), edit_id=status_id)
                await self._show_module_help(mx, event, filename)
            else:
                await utils.answer(mx, self.strings["error"].format(err="Install failed!"), edit_id=status_id)

        if not await self._security_gate(mx, event, payload, getattr(source, "is_verified", False), on_confirm=_install):
            return

        await utils.answer(mx, self.strings["downloading"], edit_id=status_id)
        if await self.repo.install(target=payload.target):
            filename = url.split("/")[-1]
            if not filename.endswith((".py", ".zip")): filename += ".py"
            await utils.answer(mx, self.strings["done"].format(name=filename), edit_id=status_id)
            await self._show_module_help(mx, event, filename)
        else:
            await utils.answer(mx, self.strings["error"].format(err="Install failed!"), edit_id=status_id)


    @loader.command(security=loader.OWNER)
    async def addrepo(self, mx, event: MessageEvent, payload: RepoPayload):
        """<url> — add repo"""
        if not payload.url:
            raise UsageError(self.strings["no_args"])

        test = await self.repo._fetch_index(payload.url)
        if not test: 
            return await utils.answer(mx, "❌ | <b>Invalid repo or index!</b>")

        async def _add_repo(ctx):
            repos = await self.repo.get_repos()
            if payload.url not in repos:
                repos.append(payload.url)
                await self._db.set("core", "community_repos", repos)
            await ctx.edit(self.strings["repo_added"].format(url=payload.url))

        if not await self._confirm_unsafe(mx, event, "repo", on_confirm=_add_repo):
            return

        repos = await self.repo.get_repos()
        if payload.url not in repos:
            repos.append(payload.url)
            await self._db.set("core", "community_repos", repos)

        await utils.answer(mx, self.strings["repo_added"].format(url=payload.url))


    @loader.command(security=loader.OWNER)
    async def delrepo(self, mx, event: MessageEvent, payload: RepoPayload):
        """<url> — delete repo"""
        if not payload.url:
            raise UsageError(self.strings["no_args"])
            
        repos = await self.repo.get_repos()
        if payload.url in repos:
            repos.remove(payload.url)
            await self._db.set("core", "community_repos", repos)
            await utils.answer(mx, self.strings["repo_removed"])


    @loader.command(security=loader.OWNER)
    async def reload(self, mx, event: MessageEvent):
        """Reload everything modules!"""
        status_id = await utils.answer(mx, self.strings["reloading"])
        await self.loader.register_all(mx)
        await utils.answer(mx, self.strings["reloaded"].format(count=len(mx.active_modules)), edit_id=status_id)


    @loader.command(security=loader.OWNER)
    async def unmd(self, mx, event: MessageEvent, payload: UnmdPayload):
        """<name> — delete module"""
        if not payload.name:
            raise UsageError(self.strings["no_args"])
            
        await self.repo.uninstall(payload.name)
        await utils.answer(mx, self.strings["unloaded"].format(name=payload.name))