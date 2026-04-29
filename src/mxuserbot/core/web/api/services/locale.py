import json
from pathlib import Path
from typing import Any

from loguru import logger

from ..constants import LOCALE_PATH

EMPTY_LOCALE = {"en": {}, "ru": {}}


class LocaleService:
    def __init__(self, locale_path: Path = LOCALE_PATH) -> None:
        self.locale_path = locale_path

    def get_locale_data(self) -> dict[str, dict[str, Any]]:
        if not self.locale_path.exists():
            logger.error("Locale file not found at %s", self.locale_path)
            return EMPTY_LOCALE

        try:
            return json.loads(self.locale_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read locale file at %s", self.locale_path)
            return EMPTY_LOCALE
