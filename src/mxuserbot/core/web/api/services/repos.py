from typing import Any

from fastapi import HTTPException

from .... import utils
from ..schemas import RepoActionRequest


class RepoService:
    async def get_repos(
        self,
        repo: Any
    ) -> list[str]:
        return await repo.get_repos()


    async def add_repo(
        self,
        req: RepoActionRequest,
        repo: Any
    ) -> dict[str, str]:
        url = utils.convert_repo_url(req.url.strip())
        test_index = await repo._fetch_index(url)
        if not test_index:
            raise HTTPException(
                status_code=400,
                detail="Invalid repository or index.json missing"
            )

        repos = await repo.get_repos()
        if url not in repos:
            repos.append(url)
            await repo.db.set("core", "community_repos", repos)

        return {"status": "ok"}


    async def remove_repo(
        self, 
        req: RepoActionRequest,
        repo: Any
    ) -> dict[str, str]:
        url = req.url.strip()
        repos = await repo.get_repos()
        if url in repos:
            repos.remove(url)
            await repo.db.set("core", "community_repos", repos)

        return {"status": "ok"}
