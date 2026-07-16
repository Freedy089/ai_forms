import os

def read_env(name, default=""):
    value = os.getenv(name, default)
    if value is None:
        return default

    cleaned = str(value).strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


NVIDIA_NIM_API_KEY = read_env("NVIDIA_NIM_API_KEY")
NVIDIA_NIM_BASE_URL = read_env("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_NIM_TIMEOUT_SECONDS = read_env("NVIDIA_NIM_TIMEOUT_SECONDS", "240")
NVIDIA_NIM_MAX_TOKENS = read_env("NVIDIA_NIM_MAX_TOKENS", "8192")
MODEL_NAME = read_env("MODEL_NAME", "nvidia/nemotron-3-ultra-550b-a55b")
TELEGRAM_BOT_TOKEN = read_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_SECRET = read_env("TELEGRAM_WEBHOOK_SECRET")
GOOGLE_CLIENT_SECRET_JSON = read_env("GOOGLE_CLIENT_SECRET_JSON")
GOOGLE_TOKEN_JSON = read_env("GOOGLE_TOKEN_JSON")
APP_BASE_URL = read_env("APP_BASE_URL")
APP_SECRET = read_env("APP_SECRET")
JOB_TTL_SECONDS = read_env("JOB_TTL_SECONDS", "3600")
CRON_SECRET = read_env("CRON_SECRET")
