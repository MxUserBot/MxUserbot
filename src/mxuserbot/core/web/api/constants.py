from pathlib import Path

API_DIR = Path(__file__).resolve().parent
WEB_DIR = API_DIR.parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
ASSETS_DIR = WEB_DIR / "assets"
LOCALE_PATH = API_DIR / "locale.json"

CRYPTO_DB_FILENAME = "sekai.db"
CRYPTO_PICKLE_KEY = "sekai_secret_pickle_key"
