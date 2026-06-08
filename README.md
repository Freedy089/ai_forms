# Hermes Quiz Builder Web

Project ini sekarang punya 3 jalur penggunaan:

- `python3 agent.py` untuk CLI lokal
- `python3 telegram_bot.py` untuk bot Telegram
- deploy ke Vercel untuk website publik

## Deploy website ke Vercel

1. Upload project ini ke Git repository.
2. Import repository ke Vercel.
3. Tambahkan environment variables berikut di Vercel Project Settings:
   - `OPENROUTER_API_KEY`
   - `MODEL_NAME` (opsional, default: `openrouter/owl-alpha`)
   - `GOOGLE_CLIENT_SECRET_JSON`
   - `GOOGLE_TOKEN_JSON`
4. Deploy.

Setelah deploy, halaman web tersedia di route `/` dan endpoint generate ada di `/api/generate`.

## Format environment variable Google

`GOOGLE_CLIENT_SECRET_JSON` harus berisi isi JSON dari `credentials.json`.

`GOOGLE_TOKEN_JSON` harus berisi isi JSON dari `token.json`.

Untuk mendapatkan `token.json`, jalankan dulu aplikasi ini secara lokal sekali dengan:

```bash
python3 agent.py
```

Setelah login Google berhasil, salin isi `token.json` ke environment variable `GOOGLE_TOKEN_JSON`.

## Catatan Netlify

Frontend statis bisa di-host di Netlify, tetapi backend Python pada repo ini tidak berjalan native di Netlify Functions.
Implementasi web pada project ini ditargetkan langsung ke Vercel karena Vercel mendukung Python Functions.
