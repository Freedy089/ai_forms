import time
import requests

import config
from agent import generate_quiz_from_prompt


API_BASE_URL = "https://api.telegram.org/bot{token}/{method}"


def build_api_url(method):
    return API_BASE_URL.format(token=config.TELEGRAM_BOT_TOKEN, method=method)


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


def handle_start_command(chat_id):
    send_message(
        chat_id,
        (
            "Kirim instruksi pembuatan soal. Contoh:\n"
            "Buatkan 10 soal kelas 10 SMK mata pelajaran Bahasa Inggris, "
            "pilihan ganda, 4 poin per soal."
        )
    )


def handle_prompt(chat_id, prompt):
    send_message(chat_id, "Permintaan diterima. Saya sedang membuat quiz...")
    result = generate_quiz_from_prompt(prompt)

    if result["mode"] == "form":
        form_links = result["form_links"]
        send_message(
            chat_id,
            (
                f"Judul: {result['title']}\n"
                f"Jumlah soal: {len(result['questions'])}\n"
                f"Poin per soal: {result['points_per_question']}\n"
                f"Link Editor: {form_links['edit_url']}\n"
                f"Link View: {form_links['view_url']}"
            )
        )
        return

    caption = (
        f"Judul: {result['title']}\n"
        f"Jumlah soal: {len(result['questions'])}\n"
        f"Poin per soal: {result['points_per_question']}"
    )
    send_document(chat_id, result["file_path"], caption)


def extract_message(update):
    return update.get("message") or update.get("edited_message") or {}


def run_bot():
    if not config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN masih kosong di config.py")

    print("Telegram bot berjalan. Tekan Ctrl+C untuk berhenti.")
    next_offset = None

    while True:
        try:
            updates = get_updates(next_offset)
            for update in updates:
                next_offset = update["update_id"] + 1
                message = extract_message(update)
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                text = (message.get("text") or "").strip()

                if not chat_id or not text:
                    continue

                if text.lower() == "/start":
                    handle_start_command(chat_id)
                    continue

                try:
                    handle_prompt(chat_id, text)
                except Exception as exc:
                    send_message(chat_id, f"Gagal memproses permintaan: {exc}")
        except KeyboardInterrupt:
            print("Telegram bot dihentikan.")
            break
        except Exception as exc:
            print(f"Loop bot error: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
