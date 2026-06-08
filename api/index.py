import base64
import hashlib
import hmac
import json
import os
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode, urlparse

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

import config
from agent import generate_quiz_from_prompt
from google_services import SCOPES


AUTH_COOKIE_NAME = "hqb_google_creds"
STATE_COOKIE_NAME = "hqb_oauth_state"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7


HTML_PAGE = """<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hermes Quiz Builder</title>
  <style>
    :root {
      --bg: #f3efe6;
      --card: rgba(255,253,248,.94);
      --ink: #18222f;
      --muted: #5a6572;
      --line: #d9cfbe;
      --accent: #0f6c5c;
      --accent-2: #d97a2b;
      --warn: #6d4c16;
      --danger: #b33a3a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217,122,43,.18), transparent 28%),
        linear-gradient(135deg, #f3efe6 0%, #efe8da 100%);
      min-height: 100vh;
    }
    .wrap { max-width: 980px; margin: 0 auto; padding: 32px 20px 56px; }
    .hero { display: grid; grid-template-columns: 1.15fr .85fr; gap: 24px; margin-bottom: 24px; }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 18px 40px rgba(24, 34, 47, 0.08);
      backdrop-filter: blur(6px);
    }
    h1 { margin: 0 0 12px; font-size: clamp(2rem, 4vw, 3.4rem); line-height: .95; letter-spacing: -.03em; }
    .badge {
      display: inline-block; padding: 8px 12px; background: #efe4cf; border-radius: 999px;
      font-size: 13px; margin-bottom: 16px;
    }
    .lead, .meta, .result-line, .status-note { color: var(--muted); line-height: 1.55; }
    .tips { margin: 0; padding-left: 18px; color: var(--muted); line-height: 1.6; }
    .toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin: 0 0 18px; }
    .pill {
      border: 1px solid var(--line); border-radius: 999px; padding: 8px 12px; background: #fff;
      font-size: 14px;
    }
    .pill.good { color: var(--accent); }
    .pill.warn { color: var(--warn); }
    form { display: grid; gap: 14px; }
    label { font-size: 14px; font-weight: 700; }
    textarea, select {
      width: 100%; border: 1px solid var(--line); border-radius: 14px;
      padding: 14px 16px; font: inherit; color: var(--ink); background: #fff;
    }
    textarea { min-height: 180px; resize: vertical; }
    .row { display: grid; grid-template-columns: 1fr 220px; gap: 14px; }
    button, .button-link {
      border: 0; border-radius: 14px; padding: 14px 18px; font: inherit; font-weight: 700;
      color: white; background: linear-gradient(135deg, var(--accent), #124c55); cursor: pointer;
      text-decoration: none; display: inline-flex; align-items: center; justify-content: center;
    }
    .button-link.secondary { background: linear-gradient(135deg, var(--accent-2), #b85b18); }
    button[disabled] { opacity: .7; cursor: wait; }
    .hidden { display: none; }
    .status {
      margin-top: 14px; padding: 14px 16px; border-radius: 14px; border: 1px solid var(--line); background: #fff;
    }
    .status.error { border-color: rgba(179,58,58,.3); background: rgba(179,58,58,.07); color: var(--danger); }
    .status.warn { border-color: rgba(109,76,22,.2); background: rgba(109,76,22,.08); color: var(--warn); }
    .result-links { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 14px; }
    @media (max-width: 760px) {
      .hero, .row { grid-template-columns: 1fr; }
      .wrap { padding: 20px 14px 40px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="card">
        <div class="badge">Hermes Quiz Builder Web</div>
        <h1>Buat Google Form quiz dari prompt biasa.</h1>
        <p class="lead">
          User login dulu dengan akun Google masing-masing. Setelah itu form dibuat langsung
          di Google Drive milik user yang sedang login.
        </p>
      </div>
      <div class="card">
        <p class="meta">Contoh prompt</p>
        <ul class="tips">
          <li>Buatkan 10 soal kelas 10 SMK mata pelajaran Bahasa Inggris, pilihan ganda, 4 poin per soal.</li>
          <li>Buat 5 soal esai kelas 8 SMP mapel IPA tentang sistem pencernaan, 2 poin per soal.</li>
          <li>Buat soal campuran untuk kelas 6 SD mata pelajaran Matematika tentang pecahan.</li>
        </ul>
      </div>
    </section>

    <section class="card">
      <div class="toolbar">
        <div id="auth-pill" class="pill warn">Status Google: belum terhubung</div>
        <a id="connect-btn" class="button-link secondary" href="/auth/google/start">Hubungkan Google</a>
        <a id="logout-btn" class="button-link hidden" href="/auth/logout">Putuskan Sesi</a>
      </div>
      <div id="auth-note" class="status warn">
        Login Google diperlukan agar form dibuat di akun Google milik Anda sendiri.
      </div>

      <form id="quiz-form">
        <div>
          <label for="prompt">Instruksi</label>
          <textarea id="prompt" name="prompt" placeholder="Tulis permintaan pembuatan soal di sini..." required></textarea>
        </div>
        <div class="row">
          <div>
            <label for="mode">Output</label>
            <select id="mode" name="mode">
              <option value="form">Google Form Quiz</option>
              <option value="word">File Word (.docx)</option>
            </select>
          </div>
          <div style="display:flex;align-items:end;">
            <button id="submit-btn" type="submit" disabled>Generate</button>
          </div>
        </div>
      </form>

      <div id="status" class="status hidden"></div>
      <div id="result" class="status hidden"></div>
    </section>
  </div>

  <script>
    const form = document.getElementById('quiz-form');
    const statusBox = document.getElementById('status');
    const resultBox = document.getElementById('result');
    const submitButton = document.getElementById('submit-btn');
    const authPill = document.getElementById('auth-pill');
    const authNote = document.getElementById('auth-note');
    const connectButton = document.getElementById('connect-btn');
    const logoutButton = document.getElementById('logout-btn');

    let isAuthenticated = false;

    function setStatus(message, kind = '') {
      statusBox.textContent = message;
      statusBox.className = 'status';
      if (kind) statusBox.classList.add(kind);
      if (!message) statusBox.classList.add('hidden');
    }

    function clearResult() {
      resultBox.innerHTML = '';
      resultBox.classList.add('hidden');
    }

    function showResultHtml(html) {
      resultBox.innerHTML = html;
      resultBox.classList.remove('hidden');
    }

    function applyAuthState(payload) {
      isAuthenticated = Boolean(payload && payload.authenticated);
      submitButton.disabled = !isAuthenticated;
      authPill.textContent = isAuthenticated ? 'Status Google: terhubung' : 'Status Google: belum terhubung';
      authPill.className = 'pill ' + (isAuthenticated ? 'good' : 'warn');
      connectButton.classList.toggle('hidden', isAuthenticated);
      logoutButton.classList.toggle('hidden', !isAuthenticated);
      authNote.textContent = isAuthenticated
        ? 'Akun Google sudah terhubung. Form akan dibuat di akun Google Anda.'
        : 'Login Google diperlukan agar form dibuat di akun Google milik Anda sendiri.';
      authNote.className = 'status ' + (isAuthenticated ? '' : 'warn');
    }

    async function loadSession() {
      try {
        const response = await fetch('/api/session');
        const payload = await response.json();
        applyAuthState(payload);
      } catch (error) {
        applyAuthState({ authenticated: false });
      }
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      clearResult();
      const prompt = document.getElementById('prompt').value.trim();
      const mode = document.getElementById('mode').value;

      if (!prompt) {
        setStatus('Instruksi tidak boleh kosong.', 'error');
        return;
      }
      if (!isAuthenticated) {
        setStatus('Hubungkan akun Google terlebih dahulu.', 'warn');
        return;
      }

      submitButton.disabled = true;
      setStatus('Permintaan sedang diproses. Ini bisa memakan beberapa detik.');

      try {
        const response = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt, mode })
        });

        if (response.status === 401) {
          const payload = await response.json();
          if (payload.auth_url) {
            window.location.href = payload.auth_url;
            return;
          }
          throw new Error(payload.error || 'Autentikasi Google diperlukan.');
        }

        if (mode === 'word' && response.ok) {
          const blob = await response.blob();
          const fileName = response.headers.get('X-File-Name') || 'quiz.docx';
          const url = window.URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = fileName;
          link.click();
          window.URL.revokeObjectURL(url);
          setStatus('File Word berhasil dibuat dan download dimulai.');
          showResultHtml('<div class="result-line">Jika download tidak mulai otomatis, ulangi permintaan atau cek popup/download browser.</div>');
          return;
        }

        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || 'Terjadi kesalahan server.');
        }

        setStatus('Quiz berhasil dibuat.');
        showResultHtml(
          '<strong>' + payload.title + '</strong>' +
          '<div class="result-line">Jumlah soal: ' + payload.question_count + '</div>' +
          '<div class="result-line">Poin per soal: ' + payload.points_per_question + '</div>' +
          '<div class="result-links">' +
            '<a class="button-link secondary" href="' + payload.edit_url + '" target="_blank" rel="noopener noreferrer">Buka Editor</a>' +
            '<a class="button-link" href="' + payload.view_url + '" target="_blank" rel="noopener noreferrer">Buka View</a>' +
          '</div>'
        );
      } catch (error) {
        setStatus(error.message || 'Gagal memproses permintaan.', 'error');
      } finally {
        submitButton.disabled = !isAuthenticated;
      }
    });

    loadSession();
  </script>
</body>
</html>
"""


def json_dumps_compact(payload):
    return json.dumps(payload, separators=(",", ":"))


def get_app_secret():
    if not config.APP_SECRET:
        raise ValueError("APP_SECRET belum diatur. Isi env APP_SECRET dengan string acak yang kuat.")
    return config.APP_SECRET.encode("utf-8")


def sign_value(value):
    signature = hmac.new(get_app_secret(), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def unsign_value(signed_value):
    if not signed_value or "." not in signed_value:
        return None
    value, signature = signed_value.rsplit(".", 1)
    expected = hmac.new(get_app_secret(), value.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return value


def encode_payload(payload):
    serialized = json_dumps_compact(payload).encode("utf-8")
    return base64.urlsafe_b64encode(serialized).decode("utf-8")


def decode_payload(value):
    decoded = base64.urlsafe_b64decode(value.encode("utf-8"))
    return json.loads(decoded.decode("utf-8"))


def serialize_credentials(credentials):
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes
    }


def build_cookie_value(payload):
    return sign_value(encode_payload(payload))


def parse_cookie_value(raw_value):
    unsigned = unsign_value(raw_value)
    if not unsigned:
        return None
    return decode_payload(unsigned)


def get_google_client_config():
    if not config.GOOGLE_CLIENT_SECRET_JSON:
        raise ValueError(
            "GOOGLE_CLIENT_SECRET_JSON belum diatur. Isi dengan JSON OAuth client type web "
            "yang memiliki redirect URI untuk website ini."
        )
    try:
        client_config = json.loads(config.GOOGLE_CLIENT_SECRET_JSON)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "GOOGLE_CLIENT_SECRET_JSON bukan JSON yang valid. "
            "Isi env ini harus berupa isi penuh file OAuth client JSON type web dari Google Cloud."
        ) from exc
    if "web" not in client_config:
        raise ValueError("GOOGLE_CLIENT_SECRET_JSON harus berisi OAuth client type 'web'.")
    return client_config


def build_base_url(headers):
    if config.APP_BASE_URL:
        return config.APP_BASE_URL.rstrip("/")
    forwarded_proto = headers.get("x-forwarded-proto")
    host = headers.get("host")
    if forwarded_proto and host:
        return f"{forwarded_proto}://{host}"
    raise ValueError("APP_BASE_URL belum diatur.")


def build_redirect_uri(headers):
    return f"{build_base_url(headers)}/auth/google/callback"


def build_flow(headers, state=None):
    flow = Flow.from_client_config(get_google_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = build_redirect_uri(headers)
    return flow


class handler(BaseHTTPRequestHandler):
    def _normalized_path(self):
        return self.path.split("?", 1)[0]

    def _query_params(self):
        return parse_qs(urlparse(self.path).query)

    def _cookies(self):
        cookie_header = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        return cookie

    def _cookie_value(self, name):
        cookies = self._cookies()
        morsel = cookies.get(name)
        return morsel.value if morsel else None

    def _set_cookie_header(self, name, value, max_age=COOKIE_MAX_AGE):
        secure = True
        return (
            f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax"
            + ("; Secure" if secure else "")
        )

    def _clear_cookie_header(self, name):
        return f"{name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax; Secure"

    def _send_response(self, status_code, body, content_type="application/json; charset=utf-8", extra_headers=None):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        if extra_headers:
            for key, value in extra_headers.items():
                if isinstance(value, list):
                    for item in value:
                        self.send_header(key, item)
                else:
                    self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status_code, payload, extra_headers=None):
        body = json.dumps(payload).encode("utf-8")
        self._send_response(status_code, body, "application/json; charset=utf-8", extra_headers=extra_headers)

    def _redirect(self, location, extra_headers=None):
        headers = {"Location": location}
        if extra_headers:
            headers.update(extra_headers)
        self._send_response(302, b"", "text/plain; charset=utf-8", extra_headers=headers)

    def _current_google_creds(self):
        raw_value = self._cookie_value(AUTH_COOKIE_NAME)
        if not raw_value:
            return None
        payload = parse_cookie_value(raw_value)
        if not payload:
            return None
        return Credentials.from_authorized_user_info(payload, SCOPES)

    def _send_session(self):
        authenticated = self._current_google_creds() is not None
        self._send_json(
            200,
            {
                "authenticated": authenticated,
                "auth_start_url": "/auth/google/start"
            }
        )

    def _start_google_auth(self):
        flow = build_flow(self.headers)
        state = secrets.token_urlsafe(32)
        authorization_url, generated_state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state
        )
        cookie_value = build_cookie_value({"state": generated_state})
        self._redirect(
            authorization_url,
            extra_headers={"Set-Cookie": self._set_cookie_header(STATE_COOKIE_NAME, cookie_value, max_age=600)}
        )

    def _complete_google_auth(self):
        raw_state_cookie = self._cookie_value(STATE_COOKIE_NAME)
        stored_state = None
        if raw_state_cookie:
            payload = parse_cookie_value(raw_state_cookie)
            if payload:
                stored_state = payload.get("state")

        query = self._query_params()
        returned_state = (query.get("state") or [""])[0]
        if not stored_state or stored_state != returned_state:
            self._send_json(400, {"error": "State OAuth tidak valid atau kedaluwarsa."})
            return

        flow = build_flow(self.headers, state=stored_state)
        authorization_response = f"{build_base_url(self.headers)}{self.path}"
        flow.fetch_token(authorization_response=authorization_response)
        creds_payload = serialize_credentials(flow.credentials)

        self._redirect(
            "/?auth=success",
            extra_headers={
                "Set-Cookie": [
                    self._set_cookie_header(AUTH_COOKIE_NAME, build_cookie_value(creds_payload)),
                    self._clear_cookie_header(STATE_COOKIE_NAME)
                ]
            }
        )

    def _logout_google_auth(self):
        self._redirect(
            "/?auth=logout",
            extra_headers={
                "Set-Cookie": [
                    self._clear_cookie_header(AUTH_COOKIE_NAME),
                    self._clear_cookie_header(STATE_COOKIE_NAME)
                ]
            }
        )

    def do_OPTIONS(self):
        self._send_response(
            204,
            b"",
            extra_headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type"
            }
        )

    def do_GET(self):
        path = self._normalized_path()
        try:
            if path in ("/", "/index.html", "/api", "/api/"):
                self._send_response(200, HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/health":
                self._send_json(200, {"ok": True})
                return
            if path == "/api/session":
                self._send_session()
                return
            if path == "/auth/google/start":
                self._start_google_auth()
                return
            if path == "/auth/google/callback":
                self._complete_google_auth()
                return
            if path == "/auth/logout":
                self._logout_google_auth()
                return

            self._send_json(404, {"error": "Halaman tidak ditemukan."})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def do_POST(self):
        path = self._normalized_path()
        if path != "/api/generate":
            self._send_json(404, {"error": "Endpoint tidak ditemukan."})
            return

        try:
            google_creds = self._current_google_creds()
            if google_creds is None:
                self._send_json(
                    401,
                    {
                        "error": "Autentikasi Google diperlukan.",
                        "auth_url": "/auth/google/start"
                    }
                )
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8") or "{}")
            prompt = str(payload.get("prompt", "")).strip()
            mode = str(payload.get("mode", "form")).strip().lower()

            if not prompt:
                self._send_json(400, {"error": "Prompt wajib diisi."})
                return
            if mode not in {"form", "word"}:
                self._send_json(400, {"error": "Mode output tidak valid."})
                return

            result = generate_quiz_from_prompt(prompt, output_mode=mode, google_creds=google_creds)

            if mode == "word":
                file_path = result["file_path"]
                file_name = os.path.basename(file_path)
                with open(file_path, "rb") as output_file:
                    file_bytes = output_file.read()
                self._send_response(
                    200,
                    file_bytes,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    {"Content-Disposition": f'attachment; filename="{file_name}"', "X-File-Name": file_name}
                )
                return

            form_links = result["form_links"]
            self._send_json(
                200,
                {
                    "title": result["title"],
                    "question_count": len(result["questions"]),
                    "points_per_question": result["points_per_question"],
                    "edit_url": form_links["edit_url"],
                    "view_url": form_links["view_url"]
                }
            )
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Body request harus JSON yang valid."})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})
