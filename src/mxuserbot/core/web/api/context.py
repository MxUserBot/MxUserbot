import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi.templating import Jinja2Templates

from .constants import TEMPLATES_DIR
from .services.auth import AuthService
from .services.locale import LocaleService
from .services.modules import ModuleService
from .services.repos import RepoService
from .services.system import SystemService


def create_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


@dataclass(slots=True)
class APIContext:
    mx: Any
    auth_event: asyncio.Event
    templates: Jinja2Templates = field(default_factory=create_templates)
    auth_service: AuthService = field(default_factory=AuthService)
    locale_service: LocaleService = field(default_factory=LocaleService)
    repo_service: RepoService = field(default_factory=RepoService)
    system_service: SystemService = field(init=False)
    module_service: ModuleService = field(init=False)

    def __post_init__(self) -> None:
        self.system_service = SystemService(self.mx)
        self.module_service = ModuleService(self.mx)
