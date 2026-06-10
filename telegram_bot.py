import time
import requests

import config
from agent import generate_quiz_from_prompt


API_BASE_URL = "https://api.telegram.org/bot{token}/{method}"


def ensure_bot_token():
    if not config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN masih kosong di config.py")


def build_api_url(method):
    ensure_bot_token()
    return API_BASE_URL.format(token=config.TELEGRAM_BOT_TOKEN, method=method)


def build_webhook_url(base_url):
    clean_base_url = (base_url or config.APP_BASE_URL or "").rstrip("/")
    if not clean_base_url:
        raise ValueError("APP_BASE_URL belum diatur. Dibutuhkan untuk Telegram webhook.")
    return f"{clean_base_url}/api/telegram/webhook"


def build_webhook_secret():
    return (config.TELEGRAM_WEBHOOK_SECRET or config.APP_SECRET or "").strip()


def call_telegram(method, data=None, files=None, timeout=60):
    response = requests.post(
        build_api_url(method),
        data=data,
        files=files,
        timeout=timeout
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error: {payload}")
    return payload


def send_message(chat_id, text):
    return call_telegram(
        "sendMessage",
        data={"chat_id": chat_id, "text": text}
    )


def send_document(chat_id, file_path, caption):
    with open(file_path, "rb") as document_file:
        return call_telegram(
            "sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": document_file}
        )


def get_updates(offset=None):
    params = {
        "timeout": 30
    }
    if offset is not None:
        params["offset"] = offset
    response = requests.get(build_api_url("getUpdates"), params=params, timeout=35)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error: {payload}")
    return payload.get("result", [])


def setup_webhook(base_url=None):
    webhook_url = build_webhook_url(base_url)
    payload = {
        "url": webhook_url,
        "drop_pending_updates": "true"
    }
    secret_token = build_webhook_secret()
    if secret_token:
        payload["secret_token"] = secret_token
    return call_telegram("setWebhook", data=payload)


def delete_webhook():
    return call_telegram("deleteWebhook", data={"drop_pending_updates": "true"})


def get_webhook_info():
    response = requests.get(build_api_url("getWebhookInfo"), timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error: {payload}")
    return payload.get("result", {})


def validate_webhook_secret(headers):
    expected_secret = build_webhook_secret()
    if not expected_secret:
        return True
    received_secret = headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    return received_secret == expected_secret


def handle_start_command(chat_id):
    send_message(
        chat_id,
        (
            "Kirim instruksi pembuatan soal. Contoh:\n"
            "Buatkan 10 soal kelas 10 SMK mata pelajaran Bahasa Inggris, "
            "pilihan ganda, 4 poin per soal.\n\n"
            "Atau untuk survey:\n"
            "Buatkan Google Form survey non-quiz untuk siswa kelas 8 tentang kebiasaan belajar, "
            "berisi 5 pertanyaan pilihan ganda dan 2 pertanyaan essay, tanpa poin dan tanpa kunci jawaban.\n\n"
            "Atau untuk Word:\n"
            "Buatkan file Word untuk kelas 9 SMP mata pelajaran Matematika, "
            "30 pilihan ganda dan 5 essay, output Word (.docx)."
        )
    )


def handle_prompt(chat_id, prompt):
    result_type = "survey" if "survey" in prompt.lower() or "survei" in prompt.lower() else "quiz/form"
    send_message(chat_id, f"Permintaan diterima. Saya sedang membuat {result_type}...")
    result = generate_quiz_from_prompt(prompt)

    if result["mode"] == "form":
        form_links = result["form_links"]
        send_message(
            chat_id,
            (
                f"Judul: {result['title']}\n"
                f"Tipe: {result['content_type']}\n"
                f"Jumlah soal: {len(result['questions'])}\n"
                f"Skema poin: {result['points_summary']}\n"
                f"Link Editor: {form_links['edit_url']}\n"
                f"Link View: {form_links['view_url']}"
            )
        )
        return

    caption = (
        f"Judul: {result['title']}\n"
        f"Tipe: {result['content_type']}\n"
        f"Jumlah soal: {len(result['questions'])}\n"
        f"Skema poin: {result['points_summary']}"
    )
    word_files = result["word_files"]
    send_document(chat_id, word_files["questions_file_path"], f"{caption}\nFile: Soal")
    send_document(chat_id, word_files["answer_key_file_path"], f"{caption}\nFile: Kunci Jawaban")


def extract_message(update):
    return update.get("message") or update.get("edited_message") or {}


def handle_update(update):
    message = extract_message(update)
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return {"ok": True, "ignored": True}

    if text.lower() == "/start":
        handle_start_command(chat_id)
        return {"ok": True, "action": "start"}

    handle_prompt(chat_id, text)
    return {"ok": True, "action": "prompt"}


def process_webhook_update(update):
    try:
        return handle_update(update)
    except Exception as exc:
        chat_id = extract_message(update).get("chat", {}).get("id")
        if chat_id:
            try:
                send_message(chat_id, f"Gagal memproses permintaan: {exc}")
            except Exception:
                pass
        return {"ok": False, "error": str(exc)}


def run_bot():
    ensure_bot_token()
    print("Telegram bot polling berjalan. Tekan Ctrl+C untuk berhenti.")
    next_offset = None

    while True:
        try:
            updates = get_updates(next_offset)
            for update in updates:
                next_offset = update["update_id"] + 1
                process_webhook_update(update)
        except KeyboardInterrupt:
            print("Telegram bot dihentikan.")
            break
        except Exception as exc:
            print(f"Loop bot error: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
