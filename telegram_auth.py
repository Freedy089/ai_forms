import json
import os
import secrets
import time

from google.oauth2.credentials import Credentials


def _storage_root():
    root = "/tmp" if os.getenv("VERCEL") else os.getcwd()
    directory = os.path.join(root, "telegram_auth_store")
    os.makedirs(directory, exist_ok=True)
    return directory


def _safe_name(value):
    return "".join(char for char in str(value) if char.isalnum() or char in {"-", "_"})


def _auth_state_path(state_token):
    return os.path.join(_storage_root(), f"state_{_safe_name(state_token)}.json")


def _chat_creds_path(chat_id):
    return os.path.join(_storage_root(), f"chat_{_safe_name(chat_id)}.json")


def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file)


def create_telegram_auth_state(chat_id, ttl_seconds=600):
    state_token = secrets.token_urlsafe(24)
    payload = {
        "tg_auth_token": state_token,
        "chat_id": str(chat_id),
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + int(ttl_seconds)
    }
    _write_json(_auth_state_path(state_token), payload)
    return state_token


def save_telegram_auth_state(state_token, payload):
    _write_json(_auth_state_path(state_token), payload)


def load_telegram_auth_state(state_token, delete_if_expired=True):
    path = _auth_state_path(state_token)
    payload = _read_json(path)
    if not payload:
        return None
    if int(time.time()) >= int(payload.get("expires_at", 0)):
        if delete_if_expired:
            delete_telegram_auth_state(state_token)
        return None
    return payload


def delete_telegram_auth_state(state_token):
    path = _auth_state_path(state_token)
    if os.path.exists(path):
        os.remove(path)


def save_telegram_user_credentials(chat_id, credentials_payload):
    payload = {
        "chat_id": str(chat_id),
        "credentials": credentials_payload,
        "saved_at": int(time.time())
    }
    _write_json(_chat_creds_path(chat_id), payload)


def load_telegram_user_credentials(chat_id):
    payload = _read_json(_chat_creds_path(chat_id))
    if not payload:
        return None
    credentials_payload = payload.get("credentials")
    if not credentials_payload:
        return None
    return Credentials.from_authorized_user_info(credentials_payload)


def has_telegram_user_credentials(chat_id):
    return load_telegram_user_credentials(chat_id) is not None
