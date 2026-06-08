import os

def read_env(name, default=""):
    value = os.getenv(name, default)
    if value is None:
        return default

    cleaned = str(value).strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


OPENROUTER_API_KEY = read_env("OPENROUTER_API_KEY")
MODEL_NAME = read_env("MODEL_NAME", "openrouter/owl-alpha")
TELEGRAM_BOT_TOKEN = read_env("TELEGRAM_BOT_TOKEN")
GOOGLE_CLIENT_SECRET_JSON = read_env("GOOGLE_CLIENT_SECRET_JSON")
GOOGLE_TOKEN_JSON = read_env("GOOGLE_TOKEN_JSON")
APP_BASE_URL = read_env("APP_BASE_URL")
APP_SECRET = read_env("APP_SECRET")
