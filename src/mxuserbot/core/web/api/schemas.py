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

class HostRequest(BaseModel):
    host: Literal["localhost", "tunnel", "0.0.0.0"] = Field(
        ...,
        description="API Mode"
    )