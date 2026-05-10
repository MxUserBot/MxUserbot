# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import re
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MXID_PATTERN = re.compile(r"^@[\w.\-]+:[\w.\-]+\.[a-zA-Z]{2,}$")


class RepoActionRequest(BaseModel):
    url: str


class LoginSchema(BaseModel):
    mxid: str
    password: str

    @field_validator("mxid")
    @classmethod
    def validate_mxid(cls, value: str) -> str:
        if not MXID_PATTERN.match(value):
            raise ValueError("Invalid format. Use @username:server.com")
        return value


class ConfigUpdateRequest(BaseModel):
    config: Dict[str, Any]


class InstallRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    target: str = Field(..., description="ID модуля или прямая ссылка")
    is_dev: bool = False


class UninstallRequest(BaseModel):
    module_id: str


class PrefixRequest(BaseModel):
    prefix: str = Field(..., min_length=1, max_length=1)

class SSOInitSchema(BaseModel):
    mxid: str
    callback_url: str

    @field_validator("mxid")
    @classmethod
    def validate_mxid(cls, value: str) -> str:
        v = value.strip().lstrip("@")
        if ":" in v:
            domain = v.split(":")[-1]
        else:
            domain = v
        if "." not in domain:
            raise ValueError("Enter a valid Matrix ID or server domain")
        return value


class HostRequest(BaseModel):
    host: Literal["localhost", "tunnel", "0.0.0.0"] = Field(
        ...,
        description="API Mode"
    )