import asyncio
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator, ConfigDict
from mautrix.types import MessageEvent

from ...core import loader, utils


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



class Meta:
    name = "LoaderModule"
    description = "Module Manager"
    version = "3.0.0"
    tags = ["system"]


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
        "done": "✅ | <b>Module <code>{name}</code> loaded successfully!</b>",
        "error": "❌ | <b>Error: <code>{err}</code></b>",
        "reloading": "⏳ | <b>Reloading all modules...</b>",
        "reloaded": "♻️ | <b>Modules reloaded. Total: {count}</b>",
        "unloaded": "✅ | <b>Module <code>{name}</code> unloaded.</b>",
        "search_header": "<b>{icon} | Found in {type} Repo: <code>{url}</code></b><br>",
        "search_item": "📦 | <b>{name}</b> (<code>{id}</code>) v<b>{version}</b><br>📥 | <b><code>.mdl {cmd_id}</code></b><br>",
        "security_warn": "⚠️ | <b>SECURITY WARNING</b><br><b>Installing from {source}. Unsafe!</b><br><i>Wait {sec} seconds...</i>",
        "dev_usage": "❌ | <b>Direct links/files require <code>dev</code> prefix.</b>",
        "no_args": "❌ | <b>Provide Module ID, URL or reply to a .py file!</b>",
        "repo_added": "✅ | <b>Repository added: <code>{url}</code></b>",
        "repo_removed": "✅ | <b>Repository removed.</b>",
        "invalid_file": "❌ | <b>ONLY .PY FILES ACCEPTED!</b>"
    }

    async def _matrix_start(self, mx):
        self.repo = loader.RepoManager(mx, self._db, self.config.get("repo_url"))

    async def _security_gate(self, mx, payload: MdlPayload, source_verified: bool, is_file: bool = False):
        is_direct = payload.target.startswith(("http", "import ", "from ")) or is_file
        
        if is_direct and not payload.is_dev:
            raise ValueError(self.strings["dev_usage"])

        if is_direct: 
            await self._wait_warning(mx, "dev", 10)
        elif not source_verified: 
            await self._wait_warning(mx, "repo", 5)

    async def _wait_warning(self, mx, warn_type, sec):
        conf_key = f"{warn_type}_warn_ok"
        if not self.config.get(conf_key):
            source_name = "community repo" if warn_type == "repo" else "direct link/file"
            await utils.answer(mx, self.strings["security_warn"].format(source=source_name, sec=sec))
            await asyncio.sleep(sec)
            self.config.set(conf_key, True)


    @loader.command(aliases=["ms"])
    async def msearch(self, mx, event: MessageEvent, payload: SearchPayload):
        """<query> — search module in repo"""
        if not payload.query:
            return await utils.answer(mx, self.strings["no_args"])

        try:
            results = await self.repo.search(payload.query)
            if not results:
                return await utils.answer(mx, self.strings["search_empty"].format(query=payload.query))

            output = []
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
                output.append(header + "".join(mods))

            await utils.answer(mx, "<br>".join(output))
        except Exception as e:
            await utils.answer(mx, self.strings["error"].format(err=str(e)))


    @loader.command()
    async def mdl(self, mx, event: MessageEvent, payload: MdlPayload):
        """[dev] <id/url/reply> — install module."""
        reply = event.content.relates_to.in_reply_to if event.content.relates_to else None

        try:
            if reply:
                await self._security_gate(mx, payload, False, is_file=True)
                msg_event = await mx.client.get_event(event.room_id, reply.event_id)
                fname, content = await self.repo.get_file_content(msg_event)
                
                if not fname.endswith(".py"):
                    return await utils.answer(mx, self.strings["invalid_file"])
                
                await utils.answer(mx, self.strings["downloading"])
                path = Path(self.loader.community_path) / fname
                path.write_bytes(content)
                await self.loader.register_module(path, mx, is_core=False)
                return await utils.answer(mx, self.strings["done"].format(name=fname))

            if not payload.target:
                return await utils.answer(mx, self.strings["no_args"])

            await utils.answer(mx, self.strings["fetching"].format(id=payload.target[:20]))
            url, source = await self.repo.resolve_and_download(payload.target)
            
            if not url:
                return await utils.answer(mx, self.strings["repo_not_found"].format(id=payload.target))
                
            await self._security_gate(mx, payload, getattr(source, "is_verified", False))

            await utils.answer(mx, self.strings["downloading"])
            if await self.repo.install(payload.target):
                filename = url.split("/")[-1]
                await utils.answer(mx, self.strings["done"].format(name=filename))
            else:
                await utils.answer(mx, self.strings["error"].format(err="Install failed!"))

        except ValueError as v:
            await utils.answer(mx, str(v))
        except Exception as e:
            await utils.answer(mx, self.strings["error"].format(err=str(e)))


    @loader.command()
    async def addrepo(self, mx, event: MessageEvent, payload: RepoPayload):
        """<url> — add repo"""
        if not payload.url:
            return await utils.answer(mx, self.strings["no_args"])

        test = await self.repo._fetch_index(payload.url)
        if not test: 
            return await utils.answer(mx, "❌ | <b>Invalid repo or index!</b>")
        
        await self._wait_warning(mx, "repo", 5)
        
        repos = await self.repo.get_repos()
        if payload.url not in repos:
            repos.append(payload.url)
            await self._db.set("core", "community_repos", repos)
            
        await utils.answer(mx, self.strings["repo_added"].format(url=payload.url))


    @loader.command()
    async def delrepo(self, mx, event: MessageEvent, payload: RepoPayload):
        """<url> — delete repo"""
        if not payload.url:
            return await utils.answer(mx, self.strings["no_args"])
            
        repos = await self.repo.get_repos()
        if payload.url in repos:
            repos.remove(payload.url)
            await self._db.set("core", "community_repos", repos)
            await utils.answer(mx, self.strings["repo_removed"])


    @loader.command()
    async def reload(self, mx, event: MessageEvent):
        """Reload everything modules!"""
        await utils.answer(mx, self.strings["reloading"])
        await self.loader.register_all(mx)
        await utils.answer(mx, self.strings["reloaded"].format(count=len(mx.active_modules)))


    @loader.command()
    async def unmd(self, mx, event: MessageEvent, payload: UnmdPayload):
        """<name> — delete module"""
        if not payload.name:
            return await utils.answer(mx, self.strings["no_args"])
            
        try:
            await self.repo.uninstall(payload.name)
            await utils.answer(mx, self.strings["unloaded"].format(name=payload.name))
        except Exception as e:
            await utils.answer(mx, self.strings["error"].format(err=str(e)))