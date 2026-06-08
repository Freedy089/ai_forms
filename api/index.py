import json
import os
from http.server import BaseHTTPRequestHandler

from agent import generate_quiz_from_prompt


HTML_PAGE = """<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hermes Quiz Builder</title>
  <style>
    :root {
      --bg: #f3efe6;
      --card: #fffdf8;
      --ink: #18222f;
      --muted: #5a6572;
      --line: #d9cfbe;
      --accent: #0f6c5c;
      --accent-2: #d97a2b;
      --danger: #b33a3a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217, 122, 43, 0.18), transparent 28%),
        linear-gradient(135deg, #f3efe6 0%, #efe8da 100%);
      min-height: 100vh;
    }
    .wrap {
      max-width: 960px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }
    .hero {
      display: grid;
      grid-template-columns: 1.2fr .8fr;
      gap: 24px;
      align-items: start;
      margin-bottom: 24px;
    }
    .hero-card, .panel {
      background: rgba(255, 253, 248, 0.92);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 18px 40px rgba(24, 34, 47, 0.08);
      backdrop-filter: blur(6px);
    }
    h1 {
      margin: 0 0 12px;
      font-size: clamp(2rem, 4vw, 3.5rem);
      line-height: 0.95;
      letter-spacing: -0.03em;
    }
    .lead, .hint, .meta, .result-line {
      color: var(--muted);
      line-height: 1.55;
    }
    .badge {
      display: inline-block;
      padding: 8px 12px;
      background: #efe4cf;
      color: var(--ink);
      border-radius: 999px;
      font-size: 13px;
      margin-bottom: 16px;
    }
    form {
      display: grid;
      gap: 14px;
    }
    label {
      font-size: 14px;
      font-weight: 700;
    }
    textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px 16px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }
    textarea {
      min-height: 180px;
      resize: vertical;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 180px;
      gap: 14px;
    }
    button {
      border: 0;
      border-radius: 14px;
      padding: 14px 18px;
      font: inherit;
      font-weight: 700;
      color: white;
      background: linear-gradient(135deg, var(--accent), #124c55);
      cursor: pointer;
    }
    button[disabled] {
      opacity: 0.7;
      cursor: wait;
    }
    .tips {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.6;
    }
    .hidden { display: none; }
    .status {
      margin-top: 14px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: #fff;
    }
    .status.error {
      border-color: rgba(179, 58, 58, 0.3);
      background: rgba(179, 58, 58, 0.07);
      color: var(--danger);
    }
    .result-links {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 14px;
    }
    .result-links a {
      text-decoration: none;
      color: white;
      background: linear-gradient(135deg, var(--accent-2), #b85b18);
      padding: 12px 14px;
      border-radius: 12px;
      font-weight: 700;
    }
    @media (max-width: 760px) {
      .hero, .row { grid-template-columns: 1fr; }
      .wrap { padding: 20px 14px 40px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-card">
        <div class="badge">Hermes Quiz Builder Web</div>
        <h1>Buat Google Form quiz dari prompt biasa.</h1>
        <p class="lead">
          Tulis instruksi seperti guru memberi briefing. Sistem akan membuat soal,
          mengatur judul sederhana, menambahkan answer key, dan memberi poin otomatis.
        </p>
      </div>
      <div class="panel">
        <p class="meta">Contoh prompt</p>
        <ul class="tips">
          <li>Buatkan 10 soal kelas 10 SMK mata pelajaran Bahasa Inggris, pilihan ganda, 4 poin per soal.</li>
          <li>Buat 5 soal esai kelas 8 SMP mapel IPA tentang sistem pencernaan, 2 poin per soal.</li>
          <li>Buat soal campuran untuk kelas 6 SD mata pelajaran Matematika tentang pecahan.</li>
        </ul>
      </div>
    </section>

    <section class="panel">
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
            <button id="submit-btn" type="submit">Generate</button>
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

    function setStatus(message, isError = false) {
      statusBox.textContent = message;
      statusBox.classList.remove('hidden', 'error');
      if (isError) statusBox.classList.add('error');
    }

    function clearResult() {
      resultBox.innerHTML = '';
      resultBox.classList.add('hidden');
    }

    function showResultHtml(html) {
      resultBox.innerHTML = html;
      resultBox.classList.remove('hidden');
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      clearResult();
      const prompt = document.getElementById('prompt').value.trim();
      const mode = document.getElementById('mode').value;

      if (!prompt) {
        setStatus('Instruksi tidak boleh kosong.', true);
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
            '<a href="' + payload.edit_url + '" target="_blank" rel="noopener noreferrer">Buka Editor</a>' +
            '<a href="' + payload.view_url + '" target="_blank" rel="noopener noreferrer">Buka View</a>' +
          '</div>'
        );
      } catch (error) {
        setStatus(error.message || 'Gagal memproses permintaan.', true);
      } finally {
        submitButton.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    def _normalized_path(self):
        return self.path.split("?", 1)[0]

    def _send_response(self, status_code, body, content_type="application/json; charset=utf-8", extra_headers=None):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self._send_response(status_code, body)

    def do_OPTIONS(self):
        self._send_response(204, b"")

    def do_GET(self):
        path = self._normalized_path()
        if path in ("/", "/index.html", "/api", "/api/"):
            self._send_response(200, HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path == "/health":
            self._send_json(200, {"ok": True})
            return

        self._send_json(404, {"error": "Halaman tidak ditemukan."})

    def do_POST(self):
        path = self._normalized_path()
        if path != "/api/generate":
            self._send_json(404, {"error": "Endpoint tidak ditemukan."})
            return

        try:
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

            result = generate_quiz_from_prompt(prompt, output_mode=mode)

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
