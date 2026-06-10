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
from agent import (
    build_batch_user_prompt,
    build_form_title,
    build_chunk_count_configs,
    detect_content_type,
    extract_requested_counts,
    extract_requested_points,
    format_counts_summary,
    format_points_summary,
    generate_quiz_from_prompt,
    generate_single_batch_quiz_data,
    should_chunk_large_request,
    validate_question_counts,
)
from docx_generator import generate_docx_file
from google_services import SCOPES
from telegram_bot import (
    delete_webhook,
    get_webhook_info,
    process_webhook_update,
    setup_webhook,
    validate_webhook_secret,
)


AUTH_COOKIE_NAME = "hqb_google_creds"
STATE_COOKIE_NAME = "hqb_oauth_state"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7
ASYNC_WORD_THRESHOLD = 30


HTML_PAGE = r"""<!doctype html>
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
    .template-box {
      margin-top: 12px;
      padding: 14px 16px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff;
      white-space: pre-wrap;
      line-height: 1.6;
    }
    .template-tabs {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .template-tab {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 10px 14px;
      background: #fff;
      color: var(--ink);
    }
    .template-tab.active {
      color: white;
      background: linear-gradient(135deg, var(--accent), #124c55);
    }
    .template-panel {
      display: none;
    }
    .template-panel.active {
      display: block;
    }
    .loading-overlay {
      position: fixed;
      inset: 0;
      background: rgba(24, 34, 47, 0.24);
      backdrop-filter: blur(8px);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 18px;
      z-index: 9999;
    }
    .loading-overlay.hidden { display: none; }
    .loading-card {
      width: min(560px, 100%);
      background: rgba(255,253,248,.98);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 24px;
      box-shadow: 0 24px 60px rgba(24, 34, 47, 0.22);
    }
    .loading-head {
      display: flex;
      gap: 16px;
      align-items: center;
      margin-bottom: 18px;
    }
    .loader-orbit {
      width: 58px;
      height: 58px;
      border-radius: 50%;
      border: 3px solid rgba(15,108,92,.15);
      border-top-color: var(--accent);
      animation: spin 1s linear infinite;
      flex: 0 0 auto;
      position: relative;
    }
    .loader-orbit::after {
      content: "";
      position: absolute;
      inset: 9px;
      border-radius: 50%;
      border: 3px dashed rgba(217,122,43,.45);
      animation: spin-reverse 2.4s linear infinite;
    }
    .loading-title {
      margin: 0;
      font-size: 1.2rem;
    }
    .loading-subtitle {
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.5;
    }
    .progress-track {
      width: 100%;
      height: 12px;
      border-radius: 999px;
      background: #ebe2d2;
      overflow: hidden;
      margin: 16px 0 10px;
    }
    .progress-fill {
      height: 100%;
      width: 12%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      transition: width 700ms ease;
      position: relative;
    }
    .progress-fill::after {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,.55), transparent);
      transform: translateX(-100%);
      animation: shimmer 1.8s linear infinite;
    }
    .progress-meta {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-size: 14px;
    }
    .batch-box {
      margin-top: 18px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #fff;
      padding: 14px 16px;
    }
    .batch-title {
      margin: 0 0 8px;
      font-weight: 700;
    }
    .batch-status {
      color: var(--muted);
      line-height: 1.5;
      margin-bottom: 10px;
    }
    .stage-list {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }
    .stage-item {
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 14px;
    }
    .stage-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #d3c6b0;
      flex: 0 0 auto;
      transition: transform 300ms ease, background 300ms ease;
    }
    .stage-item.active .stage-dot {
      background: var(--accent);
      transform: scale(1.15);
      box-shadow: 0 0 0 6px rgba(15,108,92,.12);
    }
    .stage-item.done .stage-dot {
      background: var(--accent-2);
    }
    .stage-item.active, .stage-item.done {
      color: var(--ink);
    }
    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    @keyframes spin-reverse {
      from { transform: rotate(360deg); }
      to { transform: rotate(0deg); }
    }
    @keyframes shimmer {
      from { transform: translateX(-100%); }
      to { transform: translateX(100%); }
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
      <div class="card">
        <div id="badge-text" class="badge">Hermes Quiz Builder Web</div>
        <h1 id="hero-title">Buat Google Form quiz atau survey dari prompt biasa.</h1>
        <p id="hero-lead" class="lead">
          User login dulu dengan akun Google masing-masing. Setelah itu form dibuat langsung
          di Google Drive milik user yang sedang login.
        </p>
      </div>
      <div class="card">
        <div class="toolbar" style="justify-content:space-between; margin-bottom:16px;">
          <p id="prompt-format-title" class="meta" style="margin:0;">Format prompt</p>
          <div class="toolbar" style="margin:0;">
            <button id="lang-id-btn" type="button">Bahasa Indonesia</button>
            <button id="lang-en-btn" type="button">English</button>
          </div>
        </div>
        <ul class="tips">
          <li id="tip-1">Gunakan format: kelas, mata pelajaran, materi, tingkat kesulitan, jumlah soal per tipe, dan poin per tipe.</li>
          <li id="tip-2">Tulis jumlah soal secara tegas, misalnya `50 pilihan ganda` dan `5 essay`.</li>
          <li id="tip-3">Tulis poin per tipe secara tegas, misalnya `pilihan ganda 2 poin` dan `essay 3 poin`.</li>
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

      <div class="status">
        <strong id="template-title">Template prompt</strong>
        <div id="template-note-1" class="status-note" style="margin-top:8px;">
          Gunakan format berikut agar hasil lebih rapi dan jumlah soal sesuai:
        </div>
        <div class="template-tabs">
          <button id="template-tab-quiz" class="template-tab active" type="button">Quiz</button>
          <button id="template-tab-word" class="template-tab" type="button">Word</button>
          <button id="template-tab-survey" class="template-tab" type="button">Survey</button>
        </div>
        <div id="template-panel-quiz" class="template-panel active">
          <div id="prompt-template" class="template-box">Buatkan soal untuk kelas [KELAS] dengan mata pelajaran [MATA PELAJARAN], materi [MATERI], tingkat kesulitan [RENDAH/SEDANG/TINGGI], dengan bentuk soal [JUMLAH PG] Pilihan Ganda sampai [D/E] dan [JUMLAH ESSAY] Essay, dengan poin Pilihan Ganda [POIN PG] poin dan Essay [POIN ESSAY] poin.</div>
        </div>
        <div id="template-panel-word" class="template-panel">
          <div id="word-template" class="template-box">Buatkan file Word untuk kelas [KELAS] dengan mata pelajaran [MATA PELAJARAN], materi [MATERI], tingkat kesulitan [RENDAH/SEDANG/TINGGI], dengan bentuk soal [JUMLAH PG] Pilihan Ganda sampai [D/E] dan [JUMLAH ESSAY] Essay, dengan poin Pilihan Ganda [POIN PG] poin dan Essay [POIN ESSAY] poin. Output dalam format Word (.docx).</div>
        </div>
        <div id="template-panel-survey" class="template-panel">
          <div id="survey-template" class="template-box">Buatkan Google Form survey non-quiz untuk [TARGET RESPONDEN] tentang [TOPIK], berisi [JUMLAH PG] pertanyaan pilihan ganda dan [JUMLAH ESSAY] pertanyaan essay. Ini adalah survey, jadi jangan aktifkan quiz, jangan gunakan poin, dan jangan buat kunci jawaban.</div>
        </div>
        <div id="template-note-2" class="status-note" style="margin-top:10px;">
          Format ini adalah template. Ganti bagian dalam tanda kurung siku sesuai kebutuhan Anda.
        </div>
        <div style="margin-top:12px;">
          <button id="use-template-btn" type="button">Gunakan Template Quiz</button>
          <button id="use-word-template-btn" type="button">Gunakan Template Word</button>
          <button id="use-survey-template-btn" type="button">Gunakan template survey</button>
        </div>
      </div>

      <form id="quiz-form">
        <div>
          <label id="prompt-label" for="prompt">Instruksi</label>
          <textarea id="prompt" name="prompt" placeholder="Tulis permintaan pembuatan soal di sini..." required></textarea>
        </div>
        <div class="row">
          <div>
            <label id="mode-label" for="mode">Output</label>
            <select id="mode" name="mode">
              <option id="mode-form-option" value="form">Google Form (Quiz/Survey)</option>
              <option id="mode-word-option" value="word">File Word (.docx)</option>
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

  <div id="loading-overlay" class="loading-overlay hidden" aria-live="polite">
    <div class="loading-card">
      <div class="loading-head">
        <div class="loader-orbit"></div>
        <div>
          <h2 id="loading-title" class="loading-title">Sedang memproses permintaan</h2>
          <p id="loading-subtitle" class="loading-subtitle">Sistem sedang menyiapkan prompt dan menghubungi AI.</p>
        </div>
      </div>
      <div class="progress-track">
        <div id="progress-fill" class="progress-fill"></div>
      </div>
      <div class="progress-meta">
        <span id="progress-label">Menyiapkan proses</span>
        <span id="progress-percent">12%</span>
      </div>
      <div class="batch-box">
        <p id="batch-title" class="batch-title">Progress batch</p>
        <div id="batch-status" class="batch-status">Menghitung jumlah batch dari prompt...</div>
        <div id="stage-list" class="stage-list"></div>
      </div>
    </div>
  </div>

  <script>
    const form = document.getElementById('quiz-form');
    const statusBox = document.getElementById('status');
    const resultBox = document.getElementById('result');
    const submitButton = document.getElementById('submit-btn');
    const useTemplateButton = document.getElementById('use-template-btn');
    const useWordTemplateButton = document.getElementById('use-word-template-btn');
    const useSurveyTemplateButton = document.getElementById('use-survey-template-btn');
    const templateTabQuiz = document.getElementById('template-tab-quiz');
    const templateTabWord = document.getElementById('template-tab-word');
    const templateTabSurvey = document.getElementById('template-tab-survey');
    const templatePanelQuiz = document.getElementById('template-panel-quiz');
    const templatePanelWord = document.getElementById('template-panel-word');
    const templatePanelSurvey = document.getElementById('template-panel-survey');
    const promptTemplateBox = document.getElementById('prompt-template');
    const wordTemplateBox = document.getElementById('word-template');
    const surveyTemplateBox = document.getElementById('survey-template');
    const authPill = document.getElementById('auth-pill');
    const authNote = document.getElementById('auth-note');
    const connectButton = document.getElementById('connect-btn');
    const logoutButton = document.getElementById('logout-btn');
    const loadingOverlay = document.getElementById('loading-overlay');
    const loadingTitle = document.getElementById('loading-title');
    const loadingSubtitle = document.getElementById('loading-subtitle');
    const progressFill = document.getElementById('progress-fill');
    const progressLabel = document.getElementById('progress-label');
    const progressPercent = document.getElementById('progress-percent');
    const batchStatus = document.getElementById('batch-status');
    const stageList = document.getElementById('stage-list');
    const langIdButton = document.getElementById('lang-id-btn');
    const langEnButton = document.getElementById('lang-en-btn');

    const translations = {
      id: {
        pageTitle: 'Hermes Quiz Builder',
        badgeText: 'Hermes Quiz Builder Web',
        heroTitle: 'Buat Google Form quiz atau survey dari prompt biasa.',
        heroLead: 'User login dulu dengan akun Google masing-masing. Setelah itu form dibuat langsung di Google Drive milik user yang sedang login, baik untuk quiz maupun survey.',
        promptFormatTitle: 'Format prompt',
        tip1: 'Gunakan format: kelas, mata pelajaran, materi, tingkat kesulitan, jumlah soal per tipe, dan poin per tipe.',
        tip2: 'Tulis jumlah soal secara tegas, misalnya `50 pilihan ganda` dan `5 essay`.',
        tip3: 'Tulis poin per tipe secara tegas, misalnya `pilihan ganda 2 poin` dan `essay 3 poin`.',
        tipSurvey: 'Jika hanya ingin survey, tulis jelas kata seperti `survey`, `non-quiz`, `tanpa poin`, atau `tanpa kunci jawaban`.',
        connectGoogle: 'Hubungkan Google',
        disconnectSession: 'Putuskan Sesi',
        authConnected: 'Status Google: terhubung',
        authDisconnected: 'Status Google: belum terhubung',
        authNoteConnected: 'Akun Google sudah terhubung. Form akan dibuat di akun Google Anda.',
        authNoteDisconnected: 'Login Google diperlukan agar form dibuat di akun Google milik Anda sendiri.',
        templateTitle: 'Template prompt',
        templateNote1: 'Gunakan format berikut agar hasil lebih rapi dan jumlah soal sesuai:',
        templateTabQuiz: 'Quiz',
        templateTabWord: 'Word',
        templateTabSurvey: 'Survey',
        templateText: 'Buatkan soal untuk kelas [KELAS] dengan mata pelajaran [MATA PELAJARAN], materi [MATERI], tingkat kesulitan [RENDAH/SEDANG/TINGGI], dengan bentuk soal [JUMLAH PG] Pilihan Ganda sampai [D/E] dan [JUMLAH ESSAY] Essay, dengan poin Pilihan Ganda [POIN PG] poin dan Essay [POIN ESSAY] poin.',
        wordTemplateText: 'Buatkan file Word untuk kelas [KELAS] dengan mata pelajaran [MATA PELAJARAN], materi [MATERI], tingkat kesulitan [RENDAH/SEDANG/TINGGI], dengan bentuk soal [JUMLAH PG] Pilihan Ganda sampai [D/E] dan [JUMLAH ESSAY] Essay, dengan poin Pilihan Ganda [POIN PG] poin dan Essay [POIN ESSAY] poin. Output dalam format Word (.docx).',
        surveyTemplateText: 'Buatkan Google Form survey non-quiz untuk [TARGET RESPONDEN] tentang [TOPIK], berisi [JUMLAH PG] pertanyaan pilihan ganda dan [JUMLAH ESSAY] pertanyaan essay. Ini adalah survey, jadi jangan aktifkan quiz, jangan gunakan poin, dan jangan buat kunci jawaban.',
        templateNote2: 'Format ini adalah template. Ganti bagian dalam tanda kurung siku sesuai kebutuhan Anda.',
        useTemplate: 'Gunakan Template Quiz',
        useWordTemplate: 'Gunakan Template Word',
        useSurveyTemplate: 'Gunakan template survey',
        promptLabel: 'Instruksi',
        promptPlaceholder: 'Tulis permintaan pembuatan soal di sini...',
        modeLabel: 'Output',
        modeFormOption: 'Google Form (Quiz/Survey)',
        modeWordOption: 'File Word (.docx)',
        submit: 'Generate',
        loadingTitleIdle: 'Sedang memproses permintaan',
        loadingSubtitleIdle: 'Sistem sedang menyiapkan prompt dan menghubungi AI.',
        progressLabelIdle: 'Menyiapkan proses',
        batchTitle: 'Progress batch',
        batchStatusIdle: 'Menghitung jumlah batch dari prompt...',
        outputWord: 'dokumen Word',
        outputForm: 'Google Form',
        stageAnalyze: 'Menganalisis prompt dan aturan jumlah soal',
        stageBatchMulti: 'Menyusun batch AI kecil agar request besar tetap stabil',
        stageBatchSingle: 'Menyiapkan satu batch AI',
        stageWordCompose: 'Menggabungkan hasil dan membentuk file Word',
        stageFormSend: 'Mengirim hasil ke Google Forms',
        stageWordReady: 'Menyiapkan file akhir untuk diunduh',
        stageFormReady: 'Menyelesaikan tautan editor dan view',
        preparingProcess: 'Menyiapkan proses',
        preparingPrompt: 'Sistem sedang menyiapkan prompt dan menghubungi AI.',
        estimateMulti: (batchCount, pg, esai) => 'Estimasi ' + batchCount + ' batch AI untuk ' + pg + ' PG dan ' + esai + ' esai.',
        estimateSingle: 'Permintaan diproses dalam satu batch AI.',
        processingBatch: (batchDisplay, batchCount) => 'Sedang memproses batch ' + batchDisplay + ' dari ' + batchCount + '.',
        processingDirect: 'Permintaan sedang diproses langsung ke AI.',
        batchProgressMulti: (batchDisplay, batchCount) => 'Progress batch estimasi: batch ' + batchDisplay + ' / ' + batchCount,
        batchProgressSingle: 'Progress batch estimasi: 1 / 1',
        done: 'Selesai',
        operationDone: 'Operasi selesai.',
        processingAiBatch: 'Memproses batch AI',
        wordPreparingDownload: 'Dokumen selesai dibuat. Menyiapkan unduhan.',
        asyncRunning: 'Job async sedang berjalan di server. Anda bisa menunggu di halaman ini.',
        actualBatchProgress: (doneCount, totalCount) => 'Progress batch aktual: ' + doneCount + ' / ' + totalCount,
        downloadWordFailed: 'Gagal mengunduh hasil Word.',
        fetchWordJobFailed: 'Gagal mengambil status job Word.',
        watchWordJobFailed: 'Gagal memantau job Word.',
        wordJobFailed: 'Job Word gagal diproses.',
        wordLargeDone: 'Dokumen Word besar selesai disusun.',
        twoFilesReadyStatus: 'Dua file Word berhasil disiapkan. Unduh file soal dan kunci jawaban secara terpisah.',
        twoFilesReadyLine: 'Dua file Word sudah siap diunduh.',
        downloadQuestions: 'Unduh Soal',
        downloadAnswerKey: 'Unduh Kunci Jawaban',
        serverError: 'Terjadi kesalahan server.',
        authStateInvalid: 'Sesi login Google kedaluwarsa atau tidak cocok. Silakan hubungkan Google lagi.',
        authSuccess: 'Akun Google berhasil terhubung.',
        authLogout: 'Sesi Google sudah diputus.',
        instructionRequired: 'Instruksi tidak boleh kosong.',
        connectGoogleFirst: 'Hubungkan akun Google terlebih dahulu.',
        requestProcessing: 'Permintaan sedang diproses. Ini bisa memakan beberapa detik.',
        authRequired: 'Autentikasi Google diperlukan.',
        asyncStartFailed: 'Gagal memulai job Word async.',
        asyncQueued: 'Permintaan besar dimasukkan ke job async. Sistem akan memproses per batch.',
        requestFailed: 'Gagal memproses permintaan.',
        quizCreated: 'Quiz berhasil dibuat.',
        surveyCreated: 'Survey berhasil dibuat.',
        questionCount: (count) => 'Jumlah soal: ' + count,
        pointScheme: (value) => 'Skema poin: ' + value,
        chunkedNote: 'Permintaan besar diproses dalam beberapa batch AI lalu digabung.',
        openEditor: 'Buka Editor',
        openView: 'Buka View',
        formFinished: 'Google Form selesai dibuat.',
        templateInserted: 'Template prompt dimasukkan ke kolom instruksi.',
        wordTemplateInserted: 'Template Word dimasukkan ke kolom instruksi.',
        surveyTemplateInserted: 'Template survey dimasukkan ke kolom instruksi.',
        resultTypeQuiz: 'Tipe form: Quiz',
        resultTypeSurvey: 'Tipe form: Survey',
        languageId: 'Bahasa Indonesia',
        languageEn: 'English'
      },
      en: {
        pageTitle: 'Hermes Quiz Builder',
        badgeText: 'Hermes Quiz Builder Web',
        heroTitle: 'Create Google Forms quizzes or surveys from plain prompts.',
        heroLead: 'Each user signs in with their own Google account. The generated form is created directly inside the signed-in user’s Google Drive for both quizzes and surveys.',
        promptFormatTitle: 'Prompt format',
        tip1: 'Include class level, subject, topic, difficulty, question counts per type, and points per type.',
        tip2: 'State the counts explicitly, for example `50 multiple choice` and `5 essay`.',
        tip3: 'State the points explicitly, for example `multiple choice 2 points` and `essay 3 points`.',
        tipSurvey: 'If you only want a survey, clearly include terms such as `survey`, `non-quiz`, `no points`, or `no answer key`.',
        connectGoogle: 'Connect Google',
        disconnectSession: 'Disconnect Session',
        authConnected: 'Google status: connected',
        authDisconnected: 'Google status: not connected',
        authNoteConnected: 'Your Google account is connected. Forms will be created in your Google account.',
        authNoteDisconnected: 'Google sign-in is required so the form is created in your own Google account.',
        templateTitle: 'Prompt template',
        templateNote1: 'Use the following format for cleaner results and more accurate question counts:',
        templateTabQuiz: 'Quiz',
        templateTabWord: 'Word',
        templateTabSurvey: 'Survey',
        templateText: 'Create questions for grade [GRADE] for the subject [SUBJECT], topic [TOPIC], difficulty [LOW/MEDIUM/HIGH], with [MCQ COUNT] multiple choice questions up to option [D/E] and [ESSAY COUNT] essay questions, with [MCQ POINTS] points for multiple choice and [ESSAY POINTS] points for essay.',
        wordTemplateText: 'Create a Word file for grade [GRADE] for the subject [SUBJECT], topic [TOPIC], difficulty [LOW/MEDIUM/HIGH], with [MCQ COUNT] multiple choice questions up to option [D/E] and [ESSAY COUNT] essay questions, with [MCQ POINTS] points for multiple choice and [ESSAY POINTS] points for essay. Output in Word (.docx) format.',
        surveyTemplateText: 'Create a non-quiz Google Form survey for [TARGET RESPONDENTS] about [TOPIC], containing [MCQ COUNT] multiple choice questions and [ESSAY COUNT] essay questions. This is a survey, so do not enable quiz mode, do not use points, and do not create answer keys.',
        templateNote2: 'This is a template. Replace the content inside square brackets to match your needs.',
        useTemplate: 'Use Quiz Template',
        useWordTemplate: 'Use Word Template',
        useSurveyTemplate: 'Use survey template',
        promptLabel: 'Instruction',
        promptPlaceholder: 'Write your quiz generation request here...',
        modeLabel: 'Output',
        modeFormOption: 'Google Form (Quiz/Survey)',
        modeWordOption: 'Word File (.docx)',
        submit: 'Generate',
        loadingTitleIdle: 'Processing request',
        loadingSubtitleIdle: 'The system is preparing the prompt and contacting the AI.',
        progressLabelIdle: 'Preparing process',
        batchTitle: 'Batch progress',
        batchStatusIdle: 'Estimating batch count from prompt...',
        outputWord: 'Word document',
        outputForm: 'Google Form',
        stageAnalyze: 'Analyzing the prompt and question count rules',
        stageBatchMulti: 'Building smaller AI batches for large requests',
        stageBatchSingle: 'Preparing a single AI batch',
        stageWordCompose: 'Combining results and building the Word document',
        stageFormSend: 'Sending the result to Google Forms',
        stageWordReady: 'Preparing final files for download',
        stageFormReady: 'Finishing editor and view links',
        preparingProcess: 'Preparing process',
        preparingPrompt: 'The system is preparing the prompt and contacting the AI.',
        estimateMulti: (batchCount, pg, esai) => 'Estimated ' + batchCount + ' AI batches for ' + pg + ' multiple choice and ' + esai + ' essay questions.',
        estimateSingle: 'The request is being processed in a single AI batch.',
        processingBatch: (batchDisplay, batchCount) => 'Processing batch ' + batchDisplay + ' of ' + batchCount + '.',
        processingDirect: 'The request is being processed directly by the AI.',
        batchProgressMulti: (batchDisplay, batchCount) => 'Estimated batch progress: batch ' + batchDisplay + ' / ' + batchCount,
        batchProgressSingle: 'Estimated batch progress: 1 / 1',
        done: 'Done',
        operationDone: 'Operation completed.',
        processingAiBatch: 'Processing AI batch',
        wordPreparingDownload: 'The document is ready. Preparing downloads.',
        asyncRunning: 'The async job is running on the server. You can stay on this page.',
        actualBatchProgress: (doneCount, totalCount) => 'Actual batch progress: ' + doneCount + ' / ' + totalCount,
        downloadWordFailed: 'Failed to download the Word output.',
        fetchWordJobFailed: 'Failed to fetch the Word job status.',
        watchWordJobFailed: 'Failed to monitor the Word job.',
        wordJobFailed: 'The Word job failed.',
        wordLargeDone: 'The large Word document has been assembled.',
        twoFilesReadyStatus: 'Two Word files are ready. Download the question sheet and answer key separately.',
        twoFilesReadyLine: 'Two Word files are ready for download.',
        downloadQuestions: 'Download Questions',
        downloadAnswerKey: 'Download Answer Key',
        serverError: 'A server error occurred.',
        authStateInvalid: 'The Google login session expired or is invalid. Please connect Google again.',
        authSuccess: 'Google account connected successfully.',
        authLogout: 'Google session disconnected.',
        instructionRequired: 'Instruction cannot be empty.',
        connectGoogleFirst: 'Connect your Google account first.',
        requestProcessing: 'Your request is being processed. This may take a few seconds.',
        authRequired: 'Google authentication is required.',
        asyncStartFailed: 'Failed to start the async Word job.',
        asyncQueued: 'The large request has been queued as an async job. The system will process it batch by batch.',
        requestFailed: 'Failed to process the request.',
        quizCreated: 'Quiz created successfully.',
        surveyCreated: 'Survey created successfully.',
        questionCount: (count) => 'Question count: ' + count,
        pointScheme: (value) => 'Point scheme: ' + value,
        chunkedNote: 'Large requests are processed in multiple AI batches and then merged.',
        openEditor: 'Open Editor',
        openView: 'Open View',
        formFinished: 'Google Form created successfully.',
        templateInserted: 'The prompt template has been inserted into the instruction field.',
        wordTemplateInserted: 'The Word template has been inserted into the instruction field.',
        surveyTemplateInserted: 'The survey template has been inserted into the instruction field.',
        resultTypeQuiz: 'Form type: Quiz',
        resultTypeSurvey: 'Form type: Survey',
        languageId: 'Bahasa Indonesia',
        languageEn: 'English'
      }
    };

    let isAuthenticated = false;
    let loadingTimer = null;
    let loadingState = null;
    let activeJobPoll = null;
    let currentLanguage = localStorage.getItem('hqb_lang') || 'id';

    function t(key, ...args) {
      const pack = translations[currentLanguage] || translations.id;
      const value = pack[key];
      if (typeof value === 'function') return value(...args);
      return value || key;
    }

    function applyLanguage() {
      document.documentElement.lang = currentLanguage === 'en' ? 'en' : 'id';
      document.title = t('pageTitle');
      document.getElementById('badge-text').textContent = t('badgeText');
      document.getElementById('hero-title').textContent = t('heroTitle');
      document.getElementById('hero-lead').textContent = t('heroLead');
      document.getElementById('prompt-format-title').textContent = t('promptFormatTitle');
      document.getElementById('tip-1').textContent = t('tip1');
      document.getElementById('tip-2').textContent = t('tip2');
      document.getElementById('tip-3').textContent = t('tip3');
      const tipSurveyId = 'tip-survey';
      let tipSurveyNode = document.getElementById(tipSurveyId);
      if (!tipSurveyNode) {
        tipSurveyNode = document.createElement('li');
        tipSurveyNode.id = tipSurveyId;
        document.querySelector('.tips').appendChild(tipSurveyNode);
      }
      tipSurveyNode.textContent = t('tipSurvey');
      document.getElementById('connect-btn').textContent = t('connectGoogle');
      document.getElementById('logout-btn').textContent = t('disconnectSession');
      document.getElementById('template-title').textContent = t('templateTitle');
      document.getElementById('template-note-1').textContent = t('templateNote1');
      templateTabQuiz.textContent = t('templateTabQuiz');
      templateTabWord.textContent = t('templateTabWord');
      templateTabSurvey.textContent = t('templateTabSurvey');
      document.getElementById('prompt-template').textContent = t('templateText');
      document.getElementById('word-template').textContent = t('wordTemplateText');
      document.getElementById('survey-template').textContent = t('surveyTemplateText');
      document.getElementById('template-note-2').textContent = t('templateNote2');
      document.getElementById('use-template-btn').textContent = t('useTemplate');
      document.getElementById('use-word-template-btn').textContent = t('useWordTemplate');
      document.getElementById('use-survey-template-btn').textContent = t('useSurveyTemplate');
      document.getElementById('prompt-label').textContent = t('promptLabel');
      document.getElementById('prompt').placeholder = t('promptPlaceholder');
      document.getElementById('mode-label').textContent = t('modeLabel');
      document.getElementById('mode-form-option').textContent = t('modeFormOption');
      document.getElementById('mode-word-option').textContent = t('modeWordOption');
      document.getElementById('submit-btn').textContent = t('submit');
      document.getElementById('loading-title').textContent = t('loadingTitleIdle');
      document.getElementById('loading-subtitle').textContent = t('loadingSubtitleIdle');
      document.getElementById('progress-label').textContent = t('progressLabelIdle');
      document.getElementById('batch-title').textContent = t('batchTitle');
      document.getElementById('batch-status').textContent = t('batchStatusIdle');
      langIdButton.textContent = t('languageId');
      langEnButton.textContent = t('languageEn');
      langIdButton.disabled = currentLanguage === 'id';
      langEnButton.disabled = currentLanguage === 'en';

      const sessionPayload = { authenticated: isAuthenticated };
      applyAuthState(sessionPayload);
    }

    function activateTemplateTab(tabName) {
      const tabs = [
        [templateTabQuiz, templatePanelQuiz, 'quiz'],
        [templateTabWord, templatePanelWord, 'word'],
        [templateTabSurvey, templatePanelSurvey, 'survey']
      ];
      tabs.forEach(([tabButton, panel, name]) => {
        const isActive = name === tabName;
        tabButton.classList.toggle('active', isActive);
        panel.classList.toggle('active', isActive);
      });
    }

    function switchLanguage(nextLanguage) {
      currentLanguage = nextLanguage === 'en' ? 'en' : 'id';
      localStorage.setItem('hqb_lang', currentLanguage);
      applyLanguage();
    }

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

    function estimateRequestedCounts(prompt) {
      const lowerPrompt = prompt.toLowerCase();
      const result = { pg: 0, esai: 0 };
      const pgPatterns = [
        /(\d+)\s*(?:soal\s*)?(?:pilihan\s*ganda|pg)\b/,
        /(?:pilihan\s*ganda|pg)\s*(?:sebanyak\s*)?(\d+)\s*soal\b/
      ];
      const esaiPatterns = [
        /(\d+)\s*(?:soal\s*)?(?:esai|essay)\b/,
        /(?:esai|essay)\s*(?:sebanyak\s*)?(\d+)\s*soal\b/
      ];

      for (const pattern of pgPatterns) {
        const match = lowerPrompt.match(pattern);
        if (match) {
          result.pg = Number(match[1]);
          break;
        }
      }

      for (const pattern of esaiPatterns) {
        const match = lowerPrompt.match(pattern);
        if (match) {
          result.esai = Number(match[1]);
          break;
        }
      }

      return result;
    }

    function estimateBatchCount(prompt) {
      const counts = estimateRequestedCounts(prompt);
      const pgBatches = counts.pg ? Math.ceil(counts.pg / 20) : 1;
      const esaiBatches = counts.esai ? Math.ceil(counts.esai / 5) : 1;
      return {
        counts,
        batchCount: Math.max(1, pgBatches, esaiBatches)
      };
    }

    function renderStageList(stageIndex) {
      if (!loadingState) return;
      stageList.innerHTML = '';
      loadingState.stages.forEach((stage, index) => {
        const item = document.createElement('div');
        let className = 'stage-item';
        if (index < stageIndex) className += ' done';
        else if (index === stageIndex) className += ' active';
        item.className = className;
        item.innerHTML = '<span class="stage-dot"></span><span>' + stage + '</span>';
        stageList.appendChild(item);
      });
    }

    function updateLoadingUI(progressValue, label, subtitle, stageIndex, batchText) {
      const safeProgress = Math.max(8, Math.min(progressValue, 96));
      progressFill.style.width = safeProgress + '%';
      progressPercent.textContent = Math.round(safeProgress) + '%';
      progressLabel.textContent = label;
      loadingSubtitle.textContent = subtitle;
      batchStatus.textContent = batchText;
      renderStageList(stageIndex);
    }

    function startLoadingAnimation(mode, prompt) {
      const estimate = estimateBatchCount(prompt);
      const batchCount = estimate.batchCount;
      const outputLabel = mode === 'word' ? t('outputWord') : t('outputForm');

      loadingState = {
        mode,
        prompt,
        batchCount,
        counts: estimate.counts,
        stageCursor: 0,
        stages: [
          t('stageAnalyze'),
          batchCount > 1 ? t('stageBatchMulti') : t('stageBatchSingle'),
          mode === 'word' ? t('stageWordCompose') : t('stageFormSend'),
          mode === 'word' ? t('stageWordReady') : t('stageFormReady')
        ]
      };

      loadingTitle.textContent = (currentLanguage === 'en' ? 'Creating ' : 'Sedang membuat ') + outputLabel;
      loadingOverlay.classList.remove('hidden');
      updateLoadingUI(
        12,
        t('preparingProcess'),
        t('preparingPrompt'),
        0,
        batchCount > 1
          ? t('estimateMulti', batchCount, estimate.counts.pg || 0, estimate.counts.esai || 0)
          : t('estimateSingle')
      );

      let tick = 0;
      clearInterval(loadingTimer);
      loadingTimer = setInterval(() => {
        if (!loadingState) return;
        tick += 1;
        const stageIndex = Math.min(loadingState.stages.length - 1, Math.floor(tick / 3));
        const batchDisplay = loadingState.batchCount > 1
          ? Math.min(loadingState.batchCount, 1 + Math.floor(tick / 2))
          : 1;
        const progressBase = [12, 34, 62, 82][stageIndex] || 12;
        const progressBump = Math.min(10, (tick % 3) * 3);
        const subtitle = loadingState.batchCount > 1
          ? t('processingBatch', batchDisplay, loadingState.batchCount)
          : t('processingDirect');
        const batchText = loadingState.batchCount > 1
          ? t('batchProgressMulti', batchDisplay, loadingState.batchCount)
          : t('batchProgressSingle');

        updateLoadingUI(
          progressBase + progressBump,
          loadingState.stages[stageIndex],
          subtitle,
          stageIndex,
          batchText
        );
      }, 1400);
    }

    function finishLoadingAnimation(successMessage) {
      if (!loadingState) return;
      updateLoadingUI(100, t('done'), successMessage, loadingState.stages.length, t('operationDone'));
      clearInterval(loadingTimer);
      setTimeout(() => {
        loadingOverlay.classList.add('hidden');
        loadingState = null;
      }, 900);
    }

    function stopLoadingAnimation() {
      clearInterval(loadingTimer);
      loadingTimer = null;
      loadingState = null;
      loadingOverlay.classList.add('hidden');
    }

    function updateAsyncJobLoading(payload) {
      const totalBatches = payload.total_batches || 1;
      const completedBatches = payload.completed_batches || 0;
      const progressValue = payload.progress_percent || 12;
      const stageIndex = payload.status === 'done'
        ? 4
        : payload.status === 'finalizing'
          ? 3
          : payload.status === 'processing'
            ? 1
            : 0;

      updateLoadingUI(
        progressValue,
        payload.current_step || t('processingAiBatch'),
        payload.status === 'done'
          ? t('wordPreparingDownload')
          : t('asyncRunning'),
        stageIndex,
        t('actualBatchProgress', completedBatches, totalBatches)
      );
    }

    async function downloadFile(downloadUrl) {
      const response = await fetch(downloadUrl);
      const payload = response.ok ? null : await readResponsePayload(response);
      if (!response.ok) {
        throw new Error((payload && payload.error) || t('downloadWordFailed'));
      }
      const blob = await response.blob();
      const fileName = response.headers.get('X-File-Name') || 'quiz_result.docx';
      const url = window.URL.createObjectURL(blob);
      return { url, fileName };
    }

    async function pollWordJob(statusUrl) {
      if (activeJobPoll) {
        clearTimeout(activeJobPoll);
        activeJobPoll = null;
      }

      try {
        const response = await fetch(statusUrl);
        const payload = await readResponsePayload(response);
        if (!response.ok) {
          throw new Error(payload.error || t('fetchWordJobFailed'));
        }

        updateAsyncJobLoading(payload);

        if (payload.status === 'failed') {
          stopLoadingAnimation();
          setStatus(payload.error || t('wordJobFailed'), 'error');
          return;
        }

        if (payload.status === 'done') {
          const questionsFile = await downloadFile(payload.download_questions_url);
          const answerKeyFile = await downloadFile(payload.download_answer_key_url);
          finishLoadingAnimation(t('wordLargeDone'));
          setStatus(t('twoFilesReadyStatus'));
          showResultHtml(
            '<div class="result-line">' + t('twoFilesReadyLine') + '</div>' +
            '<div class="result-links">' +
              '<a class="button-link secondary" href="' + questionsFile.url + '" download="' + questionsFile.fileName + '">' + t('downloadQuestions') + '</a>' +
              '<a class="button-link" href="' + answerKeyFile.url + '" download="' + answerKeyFile.fileName + '">' + t('downloadAnswerKey') + '</a>' +
            '</div>'
          );
          return;
        }

        activeJobPoll = setTimeout(() => pollWordJob(statusUrl), 1200);
      } catch (error) {
        stopLoadingAnimation();
        setStatus(error.message || t('watchWordJobFailed'), 'error');
      }
    }

    async function readResponsePayload(response) {
      const contentType = response.headers.get('content-type') || '';
      const rawText = await response.text();
      if (contentType.includes('application/json')) {
        return JSON.parse(rawText);
      }
      try {
        return JSON.parse(rawText);
      } catch (error) {
        return { error: rawText || t('serverError') };
      }
    }

    function applyAuthState(payload) {
      isAuthenticated = Boolean(payload && payload.authenticated);
      submitButton.disabled = !isAuthenticated;
      authPill.textContent = isAuthenticated ? t('authConnected') : t('authDisconnected');
      authPill.className = 'pill ' + (isAuthenticated ? 'good' : 'warn');
      connectButton.classList.toggle('hidden', isAuthenticated);
      logoutButton.classList.toggle('hidden', !isAuthenticated);
      authNote.textContent = isAuthenticated
        ? t('authNoteConnected')
        : t('authNoteDisconnected');
      authNote.className = 'status ' + (isAuthenticated ? '' : 'warn');
    }

    function showAuthQueryMessage() {
      const params = new URLSearchParams(window.location.search);
      const authStatus = params.get('auth');
      if (authStatus === 'state-invalid') {
        setStatus(t('authStateInvalid'), 'warn');
      } else if (authStatus === 'success') {
        setStatus(t('authSuccess'));
      } else if (authStatus === 'logout') {
        setStatus(t('authLogout'));
      }
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
        setStatus(t('instructionRequired'), 'error');
        return;
      }
      if (!isAuthenticated) {
        setStatus(t('connectGoogleFirst'), 'warn');
        return;
      }

      submitButton.disabled = true;
      setStatus(t('requestProcessing'));
      startLoadingAnimation(mode, prompt);

      try {
        const response = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt, mode })
        });

        if (response.status === 401) {
          const payload = await readResponsePayload(response);
          if (payload.auth_url) {
            window.location.href = payload.auth_url;
            return;
          }
          throw new Error(payload.error || t('authRequired'));
        }

        if (response.status === 202) {
          const payload = await readResponsePayload(response);
          if (!response.ok) {
            throw new Error(payload.error || t('asyncStartFailed'));
          }
          setStatus(t('asyncQueued'));
          updateAsyncJobLoading(payload);
          pollWordJob(payload.status_url);
          return;
        }

        if (mode === 'word' && response.ok) {
          const payload = await readResponsePayload(response);
          if (!response.ok) {
            throw new Error(payload.error || t('serverError'));
          }
          const questionsFile = await downloadFile(payload.download_questions_url);
          const answerKeyFile = await downloadFile(payload.download_answer_key_url);
          setStatus(t('twoFilesReadyStatus'));
          showResultHtml(
            '<div class="result-line">' + t('twoFilesReadyLine') + '</div>' +
            '<div class="result-links">' +
              '<a class="button-link secondary" href="' + questionsFile.url + '" download="' + questionsFile.fileName + '">' + t('downloadQuestions') + '</a>' +
              '<a class="button-link" href="' + answerKeyFile.url + '" download="' + answerKeyFile.fileName + '">' + t('downloadAnswerKey') + '</a>' +
            '</div>'
          );
          finishLoadingAnimation(t('wordPreparingDownload'));
          return;
        }

        const payload = await readResponsePayload(response);
        if (!response.ok) {
          throw new Error(payload.error || t('serverError'));
        }

        setStatus(payload.content_type === 'survey' ? t('surveyCreated') : t('quizCreated'));
        showResultHtml(
          '<strong>' + payload.title + '</strong>' +
          '<div class="result-line">' + (payload.content_type === 'survey' ? t('resultTypeSurvey') : t('resultTypeQuiz')) + '</div>' +
          '<div class="result-line">' + t('questionCount', payload.question_count) + '</div>' +
          '<div class="result-line">' + t('pointScheme', payload.points_summary) + '</div>' +
          (payload.chunked_generation ? '<div class="result-line">' + t('chunkedNote') + '</div>' : '') +
          '<div class="result-links">' +
            '<a class="button-link secondary" href="' + payload.edit_url + '" target="_blank" rel="noopener noreferrer">' + t('openEditor') + '</a>' +
            '<a class="button-link" href="' + payload.view_url + '" target="_blank" rel="noopener noreferrer">' + t('openView') + '</a>' +
          '</div>'
        );
        finishLoadingAnimation(t('formFinished'));
      } catch (error) {
        stopLoadingAnimation();
        setStatus(error.message || t('requestFailed'), 'error');
      } finally {
        submitButton.disabled = !isAuthenticated;
      }
    });

    useTemplateButton.addEventListener('click', () => {
      const promptBox = document.getElementById('prompt');
      promptBox.value = promptTemplateBox.textContent.trim();
      promptBox.focus();
      promptBox.setSelectionRange(promptBox.value.length, promptBox.value.length);
      setStatus(t('templateInserted'));
    });

    useWordTemplateButton.addEventListener('click', () => {
      const promptBox = document.getElementById('prompt');
      const modeBox = document.getElementById('mode');
      promptBox.value = wordTemplateBox.textContent.trim();
      modeBox.value = 'word';
      promptBox.focus();
      promptBox.setSelectionRange(promptBox.value.length, promptBox.value.length);
      setStatus(t('wordTemplateInserted'));
    });

    useSurveyTemplateButton.addEventListener('click', () => {
      const promptBox = document.getElementById('prompt');
      promptBox.value = surveyTemplateBox.textContent.trim();
      promptBox.focus();
      promptBox.setSelectionRange(promptBox.value.length, promptBox.value.length);
      setStatus(t('surveyTemplateInserted'));
    });

    templateTabQuiz.addEventListener('click', () => activateTemplateTab('quiz'));
    templateTabWord.addEventListener('click', () => activateTemplateTab('word'));
    templateTabSurvey.addEventListener('click', () => activateTemplateTab('survey'));

    langIdButton.addEventListener('click', () => switchLanguage('id'));
    langEnButton.addEventListener('click', () => switchLanguage('en'));

    activateTemplateTab('quiz');
    applyLanguage();
    showAuthQueryMessage();
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
    return base64.urlsafe_b64encode(serialized).decode("utf-8").rstrip("=")


def decode_payload(value):
    padding = "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode((value + padding).encode("utf-8"))
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


def get_job_store_dir():
    directory = os.path.join("/tmp" if os.getenv("VERCEL") else os.getcwd(), "job_store")
    os.makedirs(directory, exist_ok=True)
    return directory


def get_job_ttl_seconds():
    raw_ttl = getattr(config, "JOB_TTL_SECONDS", 3600)
    try:
        return max(60, int(raw_ttl))
    except (TypeError, ValueError):
        return 3600


def now_timestamp():
    import time
    return int(time.time())


def get_job_file_path(job_id):
    safe_job_id = "".join(char for char in job_id if char.isalnum() or char in {"-", "_"})
    return os.path.join(get_job_store_dir(), f"{safe_job_id}.json")


def delete_file_if_exists(file_path):
    if file_path and os.path.exists(file_path):
        os.remove(file_path)


def delete_job_artifacts(job_state):
    word_files = job_state.get("word_files") or {}
    delete_file_if_exists(word_files.get("questions_file_path"))
    delete_file_if_exists(word_files.get("answer_key_file_path"))
    delete_file_if_exists(get_job_file_path(job_state["job_id"]))


def save_job_state(job_state):
    with open(get_job_file_path(job_state["job_id"]), "w", encoding="utf-8") as job_file:
        json.dump(job_state, job_file)


def is_job_expired(job_state):
    return now_timestamp() >= int(job_state.get("expires_at", 0))


def load_job_state(job_id, delete_if_expired=True):
    file_path = get_job_file_path(job_id)
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as job_file:
            job_state = json.load(job_file)
    except (OSError, json.JSONDecodeError):
        delete_file_if_exists(file_path)
        return None
    if delete_if_expired and is_job_expired(job_state):
        delete_job_artifacts(job_state)
        return None
    return job_state


def cleanup_expired_jobs():
    removed = 0
    for file_name in os.listdir(get_job_store_dir()):
        if not file_name.endswith(".json"):
            continue
        file_path = os.path.join(get_job_store_dir(), file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as job_file:
                job_state = json.load(job_file)
        except (OSError, json.JSONDecodeError):
            delete_file_if_exists(file_path)
            removed += 1
            continue
        if is_job_expired(job_state):
            delete_job_artifacts(job_state)
            removed += 1
    return removed


def create_job_download_files(job_state):
    return job_state["word_files"]


def create_async_word_job(prompt):
    content_type = detect_content_type(prompt)
    point_config = extract_requested_points(prompt)
    count_config = extract_requested_counts(prompt)
    chunk_configs = build_chunk_count_configs(count_config)
    job_id = secrets.token_urlsafe(12)
    created_at = now_timestamp()
    job_state = {
        "job_id": job_id,
        "prompt": prompt,
        "content_type": content_type,
        "point_config": point_config,
        "count_config": count_config,
        "chunk_configs": chunk_configs,
        "completed_batches": 0,
        "total_batches": len(chunk_configs),
        "questions": [],
        "title": None,
        "points_summary": format_points_summary(point_config, content_type),
        "counts_summary": format_counts_summary(count_config),
        "status": "queued",
        "current_step": "Masuk antrean batch AI",
        "error": "",
        "chunked_generation": True,
        "word_files": None,
        "created_at": created_at,
        "expires_at": created_at + get_job_ttl_seconds()
    }
    save_job_state(job_state)
    return job_state


def create_completed_word_job(prompt, title, questions, point_config, count_config, word_files, chunked_generation=False, content_type="quiz"):
    job_id = secrets.token_urlsafe(12)
    created_at = now_timestamp()
    job_state = {
        "job_id": job_id,
        "prompt": prompt,
        "content_type": content_type,
        "point_config": point_config,
        "count_config": count_config,
        "chunk_configs": [],
        "completed_batches": 0,
        "total_batches": 0,
        "questions": questions,
        "title": title,
        "points_summary": format_points_summary(point_config, content_type),
        "counts_summary": format_counts_summary(count_config),
        "status": "done",
        "current_step": "Selesai",
        "error": "",
        "chunked_generation": chunked_generation,
        "word_files": word_files,
        "created_at": created_at,
        "expires_at": created_at + get_job_ttl_seconds()
    }
    save_job_state(job_state)
    return job_state


def build_job_status_response(job_state, base_url):
    progress_percent = 12
    if job_state["status"] == "done":
        progress_percent = 100
    elif job_state["status"] == "finalizing":
        progress_percent = 90
    elif job_state["total_batches"] > 0:
        progress_percent = min(88, 16 + int((job_state["completed_batches"] / job_state["total_batches"]) * 60))

    payload = {
        "job_id": job_state["job_id"],
        "status": job_state["status"],
        "current_step": job_state["current_step"],
        "completed_batches": job_state["completed_batches"],
        "total_batches": job_state["total_batches"],
        "progress_percent": progress_percent,
        "points_summary": job_state["points_summary"],
        "counts_summary": job_state["counts_summary"],
        "chunked_generation": job_state.get("chunked_generation", False),
        "content_type": job_state.get("content_type", "quiz"),
        "expires_at": job_state["expires_at"]
    }
    if job_state.get("title"):
        payload["title"] = job_state["title"]
    if job_state.get("error"):
        payload["error"] = job_state["error"]
    if job_state["status"] == "done":
        payload["download_questions_url"] = f"{base_url}/api/jobs/{job_state['job_id']}/download/questions"
        payload["download_answer_key_url"] = f"{base_url}/api/jobs/{job_state['job_id']}/download/answer-key"
    return payload


def advance_async_word_job(job_state):
    if job_state["status"] in {"done", "failed"}:
        return job_state

    try:
        next_batch_index = job_state["completed_batches"]
        if next_batch_index < job_state["total_batches"]:
            chunk_count_config = job_state["chunk_configs"][next_batch_index]
            job_state["status"] = "processing"
            job_state["current_step"] = f"Memproses batch {next_batch_index + 1} dari {job_state['total_batches']}"
            save_job_state(job_state)

            batch_prompt = build_batch_user_prompt(
                job_state["prompt"],
                chunk_count_config,
                next_batch_index + 1,
                job_state["total_batches"]
            )
            quiz_data, questions = generate_single_batch_quiz_data(
                batch_prompt,
                job_state["point_config"],
                chunk_count_config,
                job_state.get("content_type", "quiz")
            )
            if not job_state.get("title"):
                job_state["title"] = build_form_title(
                    job_state["prompt"],
                    quiz_data.get("judul", "Survey" if job_state.get("content_type") == "survey" else "Quiz"),
                    job_state.get("content_type", "quiz")
                )
            job_state["questions"].extend(questions)
            job_state["completed_batches"] += 1

        if job_state["completed_batches"] >= job_state["total_batches"]:
            job_state["status"] = "finalizing"
            job_state["current_step"] = "Menggabungkan batch dan menyusun dokumen Word"
            validate_question_counts(job_state["questions"], job_state["count_config"])
            job_state["word_files"] = generate_docx_file(job_state["title"] or "Quiz", job_state["questions"])
            job_state["status"] = "done"
            job_state["current_step"] = "Selesai"

        save_job_state(job_state)
        return job_state
    except Exception as exc:
        job_state["status"] = "failed"
        job_state["error"] = str(exc)
        job_state["current_step"] = "Job gagal"
        save_job_state(job_state)
        return job_state


def is_cron_request_authorized(headers):
    expected_secret = getattr(config, "CRON_SECRET", "") or ""
    if not expected_secret:
        return False
    auth_header = headers.get("Authorization", "")
    return secrets.compare_digest(auth_header, f"Bearer {expected_secret}")


def is_admin_request_authorized(headers):
    expected_secret = getattr(config, "APP_SECRET", "") or ""
    if not expected_secret:
        return False
    auth_header = headers.get("Authorization", "")
    return secrets.compare_digest(auth_header, f"Bearer {expected_secret}")


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
        authorization_url, generated_state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )
        cookie_payload = {
            "state": generated_state
        }
        code_verifier = getattr(flow, "code_verifier", None)
        if code_verifier:
            cookie_payload["code_verifier"] = code_verifier
        cookie_value = build_cookie_value(cookie_payload)
        self._redirect(
            authorization_url,
            extra_headers={"Set-Cookie": self._set_cookie_header(STATE_COOKIE_NAME, cookie_value, max_age=600)}
        )

    def _complete_google_auth(self):
        raw_state_cookie = self._cookie_value(STATE_COOKIE_NAME)
        stored_state = None
        stored_code_verifier = None
        if raw_state_cookie:
            payload = parse_cookie_value(raw_state_cookie)
            if payload:
                stored_state = payload.get("state")
                stored_code_verifier = payload.get("code_verifier")

        query = self._query_params()
        returned_state = (query.get("state") or [""])[0]
        if not stored_state or stored_state != returned_state:
            self._redirect(
                "/?auth=state-invalid",
                extra_headers={
                    "Set-Cookie": self._clear_cookie_header(STATE_COOKIE_NAME)
                }
            )
            return

        flow = build_flow(self.headers, state=stored_state)
        if stored_code_verifier:
            flow.code_verifier = stored_code_verifier
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
            cleanup_expired_jobs()
            if path in ("/", "/index.html", "/api", "/api/"):
                self._send_response(200, HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/health":
                self._send_json(200, {"ok": True})
                return
            if path == "/api/cron/cleanup-jobs":
                if not is_cron_request_authorized(self.headers):
                    self._send_json(401, {"error": "Unauthorized"})
                    return
                removed_jobs = cleanup_expired_jobs()
                self._send_json(200, {"ok": True, "removed_jobs": removed_jobs, "ttl_seconds": get_job_ttl_seconds()})
                return
            if path == "/api/session":
                self._send_session()
                return
            if path == "/api/telegram/webhook-info":
                if not is_admin_request_authorized(self.headers):
                    self._send_json(401, {"error": "Unauthorized"})
                    return
                self._send_json(200, {"ok": True, "webhook_info": get_webhook_info()})
                return
            if path == "/api/telegram/setup-webhook":
                if not is_admin_request_authorized(self.headers):
                    self._send_json(401, {"error": "Unauthorized"})
                    return
                self._send_json(200, {"ok": True, "result": setup_webhook(build_base_url(self.headers))})
                return
            if path == "/api/telegram/delete-webhook":
                if not is_admin_request_authorized(self.headers):
                    self._send_json(401, {"error": "Unauthorized"})
                    return
                self._send_json(200, {"ok": True, "result": delete_webhook()})
                return
            if path.startswith("/api/jobs/"):
                self._handle_job_get(path)
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
        if path == "/api/telegram/webhook":
            self._handle_telegram_webhook()
            return
        if path != "/api/generate":
            self._send_json(404, {"error": "Endpoint tidak ditemukan."})
            return

        try:
            cleanup_expired_jobs()
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

            requested_counts = extract_requested_counts(prompt)
            total_requested = (requested_counts["pg"] or 0) + (requested_counts["esai"] or 0)
            if mode == "word" and total_requested > ASYNC_WORD_THRESHOLD and should_chunk_large_request(requested_counts):
                job_state = create_async_word_job(prompt)
                base_url = build_base_url(self.headers)
                self._send_json(
                    202,
                    {
                        **build_job_status_response(job_state, base_url),
                        "status_url": f"{base_url}/api/jobs/{job_state['job_id']}"
                    }
                )
                return

            result = generate_quiz_from_prompt(prompt, output_mode=mode, google_creds=google_creds)

            if mode == "word":
                word_files = result["word_files"]
                point_config = extract_requested_points(prompt)
                count_config = extract_requested_counts(prompt)
                job_state = create_completed_word_job(
                    prompt=prompt,
                    title=result["title"],
                    questions=result["questions"],
                    point_config=point_config,
                    count_config=count_config,
                    word_files=word_files,
                    chunked_generation=result.get("chunked_generation", False),
                    content_type=result.get("content_type", "quiz")
                )
                base_url = build_base_url(self.headers)
                self._send_json(
                    200,
                    {
                        **build_job_status_response(job_state, base_url),
                        "title": result["title"],
                        "question_count": len(result["questions"]),
                        "content_type": result["content_type"],
                        "status_url": f"{base_url}/api/jobs/{job_state['job_id']}"
                    }
                )
                return

            form_links = result["form_links"]
            self._send_json(
                200,
                {
                    "title": result["title"],
                    "question_count": len(result["questions"]),
                    "content_type": result["content_type"],
                    "points_summary": result["points_summary"],
                    "chunked_generation": result["chunked_generation"],
                    "edit_url": form_links["edit_url"],
                    "view_url": form_links["view_url"]
                }
            )
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Body request harus JSON yang valid."})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _handle_telegram_webhook(self):
        try:
            if not validate_webhook_secret(self.headers):
                self._send_json(401, {"error": "Unauthorized"})
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8") or "{}")
            result = process_webhook_update(payload)
            self._send_json(200, result)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Body webhook Telegram harus JSON yang valid."})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _handle_job_get(self, path):
        base_url = build_base_url(self.headers)
        if "/download/" in path:
            job_id = path.split("/api/jobs/", 1)[1].split("/download/", 1)[0]
            file_kind = path.rsplit("/download/", 1)[1]
            job_state = load_job_state(job_id)
            if not job_state:
                self._send_json(404, {"error": "Job tidak ditemukan atau sudah kedaluwarsa."})
                return
            if job_state["status"] != "done" or not job_state.get("word_files"):
                self._send_json(409, {"error": "File hasil belum siap diunduh."})
                return

            word_files = create_job_download_files(job_state)
            if file_kind == "questions":
                target_path = word_files["questions_file_path"]
            elif file_kind == "answer-key":
                target_path = word_files["answer_key_file_path"]
            else:
                self._send_json(404, {"error": "Jenis file tidak ditemukan."})
                return

            with open(target_path, "rb") as output_file:
                file_bytes = output_file.read()
            self._send_response(
                200,
                file_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                {
                    "Content-Disposition": f'attachment; filename="{os.path.basename(target_path)}"',
                    "X-File-Name": os.path.basename(target_path)
                }
            )
            return

        job_id = path.split("/api/jobs/", 1)[1]
        job_state = load_job_state(job_id)
        if not job_state:
            self._send_json(404, {"error": "Job tidak ditemukan atau sudah kedaluwarsa."})
            return

        if job_state["status"] not in {"done", "failed"}:
            job_state = advance_async_word_job(job_state)

        self._send_json(200, build_job_status_response(job_state, base_url))
