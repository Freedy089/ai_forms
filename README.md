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
   - `APP_BASE_URL`
   - `APP_SECRET`
4. Deploy.

Setelah deploy, halaman web tersedia di route `/` dan endpoint generate ada di `/api/generate`.

## OAuth Google untuk website

Untuk website, user harus login dengan akun Google masing-masing. Form akan dibuat di akun Google user yang sedang login.

Karena itu, `GOOGLE_CLIENT_SECRET_JSON` harus berisi isi penuh file OAuth client type `web`, bukan token user global.

Langkah setup di Google Cloud Console:

1. Buat OAuth Client ID type `Web application`.
2. Tambahkan Authorized Redirect URI:

```bash
https://domain-website-anda/auth/google/callback
```

3. Simpan isi file JSON client tersebut ke environment variable `GOOGLE_CLIENT_SECRET_JSON`.
4. Isi `APP_BASE_URL` dengan domain website Anda, misalnya:

```bash
https://ai-forms.vercel.app
```

5. Isi `APP_SECRET` dengan string acak panjang untuk signing cookie sesi.

Catatan penting:

- Redirect URI harus sama persis dengan yang didaftarkan di Google.
- Website tidak lagi memakai `token.json` global untuk flow web.
- `GOOGLE_TOKEN_JSON` masih bisa dipakai untuk mode lokal CLI jika Anda ingin mempertahankannya.

## Catatan Netlify

Frontend statis bisa di-host di Netlify, tetapi backend Python pada repo ini tidak berjalan native di Netlify Functions.
Implementasi web pada project ini ditargetkan langsung ke Vercel karena Vercel mendukung Python Functions.
