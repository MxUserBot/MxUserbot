from pathlib import Path
from typing import Any

from mautrix.types import MessageEvent
from ...core import loader, utils

REPO_RAW_URL = "https://raw.githubusercontent.com/MxUserBot/mx-modules/main"


class Meta:
    name = "LoaderModule"
    _cls_doc = "Downloads, manages, and reloads modules from a remote repository."
    version = "1.1.0"
    tags = ["system"]


@loader.tds
class LoaderModule(loader.Module):
    """Module manager for Sekai Matrix UserBot"""

    strings = {
        "no_url_or_id": "❌ Provide a URL or Module ID from the repository",
        "downloading": "⏳ Downloading module...",
        "fetching_repo": "⏳ Searching for module <code>{id}</code> in the repository...",
        "repo_not_found": "❌ Module <code>{id}</code> not found in the repository.",
        "done": "✅ Module loaded: <code>{name}</code>",
        "error": "❌ Error: <code>{err}</code>",
        
        "reloaded_header": "<b>♻️ Modules reloaded:</b><br>",
        "module_item": "▫️ <code>{name}</code><br>",
        
        "no_name": "❌ Provide a module filename to unload (without .py)",
        "not_found": "❌ Module <code>{name}</code> not found among active modules",
        "unloaded": "✅ Module <code>{name}</code> successfully unloaded and deleted",

        "search_no_query": "❌ Provide search query. Example: <code>.msearch music</code>",
        "search_header": "<b>🔍 Search results for «{query}»:</b><br><br>",
        "search_item": "📦 | <b>{name}</b> (<code>{id}</code>) v{version}<br>📝 <i>{desc}</i><br>📥 Install: <code>.mdl {id}</code><br><br>",
        "search_empty": "❌ | No results found for <code>{query}</code>.",

        "repo_fetching_list": "⏳ | <b>Fetching module list...</b>",
        "repo_list_empty": "❌ | <b>Repository is empty or unavailable.</b>",
        "repo_list_header": "<b>📦 | Official Repository:</b><br><details><summary>Expand list ({count} items)</summary><br>",
        "repo_list_item": "▫️ <b>{id}</b> — <small><i>{desc}</i></small><br>"
    }

    @loader.command()
    async def mdl(self, mx: Any, event: MessageEvent):
        """<url/id> — Download a module via link or ID"""
        arg = await utils.get_args_raw(mx, event)
        
        if not arg:
            return await utils.answer(mx, self.strings["no_url_or_id"])
        
        arg = arg.strip()
        is_url = arg.startswith(("http://", "https://"))

        try:
            if not is_url:
                await utils.answer(mx, self.strings["fetching_repo"].format(id=arg))
                
                # Используем utils.request для получения индекса
                repo_data = await utils.request(f"{REPO_RAW_URL}/index.json", return_type="json")
                if not repo_data:
                    raise Exception("Failed to fetch repository index")
                
                mod_info = next((m for m in repo_data.get("modules", []) if m.get("id") == arg), None)
                
                if not mod_info:
                    return await utils.answer(mx, self.strings["repo_not_found"].format(id=arg))

                download_url = f"{REPO_RAW_URL}/modules/{mod_info['path']}"
                filename = mod_info["path"]
            else:
                download_url = arg
                filename = Path(download_url).name
                if not filename.endswith(".py"):
                    filename += ".py"

            await utils.answer(mx, self.strings["downloading"])
            
            # Скачиваем сам код
            code = await utils.request(download_url, return_type="text")
            if not code:
                raise Exception("Failed to download module code")

            path = Path(self.loader.community_path) / filename
            path.write_text(code, encoding="utf-8")

            # Регистрация модуля в ядре
            await self.loader.register_module(path, mx, is_core=False)

            await utils.answer(mx, self.strings["done"].format(name=filename))

        except Exception as e:
            await utils.answer(mx, self.strings["error"].format(err=str(e)))

    @loader.command()
    async def mrepo(self, mx: Any, event: MessageEvent):
        """Show full module list from official repository"""
        await utils.answer(mx, self.strings["repo_fetching_list"])

        try:
            repo_data = await utils.request(f"{REPO_RAW_URL}/index.json", return_type="json")
            print(repo_data)
            if not repo_data:
                raise Exception("Failed to fetch repository data")

            modules = repo_data.get("modules", [])
            if not modules:
                return await utils.answer(mx, self.strings["repo_list_empty"])

            modules.sort(key=lambda x: x.get("id", ""))

            msg = self.strings["repo_list_header"].format(count=len(modules))
            for mod in modules:
                msg += self.strings["repo_list_item"].format(
                    id=mod.get("id", "unknown"),
                    desc=mod.get("description", "No description")
                )
            msg += "</details>"

            await utils.answer(mx, msg)
        except Exception as e:
            print(e)
            await utils.answer(mx, self.strings["error"].format(err=str(e)))

    @loader.command()
    async def msearch(self, mx: Any, event: MessageEvent):
        """<query> — Search modules in the official repository"""
        query = await utils.get_args_raw(mx, event)
        if not query:
            return await utils.answer(mx, self.strings["search_no_query"])

        query = query.strip().lower()

        try:
            repo_data = await utils.request(f"{REPO_RAW_URL}/index.json", return_type="json")
            if not repo_data:
                raise Exception("Failed to fetch repository data")

            results = []
            for mod in repo_data.get("modules", []):
                search_text = f"{mod.get('id', '')} {mod.get('name', '')} {mod.get('description', '')} {' '.join(mod.get('tags', []))}".lower()
                if query in search_text:
                    results.append(mod)

            if not results:
                return await utils.answer(mx, self.strings["search_empty"].format(query=query))

            msg = self.strings["search_header"].format(query=query)
            for mod in results:
                msg += self.strings["search_item"].format(
                    name=mod.get("name"),
                    id=mod.get("id"),
                    version=mod.get("version"),
                    desc=mod.get("description")
                )

            await utils.answer(mx, msg)
        except Exception as e:
            await utils.answer(mx, self.strings["error"].format(err=str(e)))

    @loader.command()
    async def reload(self, mx: Any, event: MessageEvent):
        """Reload all active modules"""
        # Сначала отправляем сообщение, так как после выгрузки модулей мы можем потерять контекст
        await utils.answer(mx, "⏳ Reloading all modules...")
        
        active_names = list(mx.active_modules.keys())

        for name in active_names:
            try:
                await self.loader.unload_module(name, mx)
            except Exception:
                continue

        await self.loader.register_all(mx)

        msg = self.strings["reloaded_header"]
        for name in mx.active_modules.keys():
            msg += self.strings["module_item"].format(name=name)

        await utils.answer(mx, msg)

    @loader.command()
    async def unmd(self, mx: Any, event: MessageEvent):
        """<filename> — Unload and permanently delete a community module"""
        name = await utils.get_args_raw(mx, event)

        if not name:
            return await utils.answer(mx, self.strings["no_name"])
        
        name = name.strip()

        if name not in mx.active_modules:
            return await utils.answer(mx, self.strings["not_found"].format(name=name))
        
        try:
            await self.loader.unload_module(name, mx)

            path = Path(self.loader.community_path) / f"{name}.py"
            if path.exists():
                path.unlink()

            await utils.answer(mx, self.strings["unloaded"].format(name=name))
        except Exception as e:
            await utils.answer(mx, self.strings["error"].format(err=str(e)))