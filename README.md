# Hermes Quiz Builder

Hermes Quiz Builder is an AI-assisted quiz and survey generation project that turns natural-language prompts into:

- Google Forms quizzes
- Google Forms surveys
- Word documents for question sheets
- Separate Word documents for answer keys
- Telegram bot responses
- A web app deployable to Vercel

## What this project is

This project helps teachers, tutors, and education operators generate structured assessments faster.  
Instead of manually writing dozens of questions, formatting answer keys, and rebuilding everything again inside Google Forms, the user can write one prompt and let the system generate the quiz package automatically.

The project supports:

- multiple choice and essay questions
- non-quiz survey forms without grading
- per-question-type point settings
- Google Forms quiz mode with answer keys
- automatic form title generation
- Word export with separated question and answer-key files
- async handling for large Word generation jobs
- Google OAuth so each web user creates forms in their own Google account

## Purpose

The main goal is to reduce the repetitive work involved in preparing school assessments while keeping the output usable in real teaching workflows.

This project is designed to:

- speed up quiz authoring
- reduce manual formatting work
- produce Google Forms directly in the owner’s account
- keep Word exports ready for print or editing
- support both small and large generation requests

## Problems this project solves

Before this workflow, users usually face several problems:

1. Writing prompts is easy, but turning the result into a real Google Form still takes manual work.
2. Generated quizzes often do not preserve clear point rules for different question types.
3. Large question requests can fail or time out if sent to the AI as one big request.
4. Web users should not share one global Google token; each user must authenticate with their own Google account.
5. Teachers often need both editable digital forms and printable Word files.
6. Temporary generated files can waste storage if they are never cleaned up.

Hermes Quiz Builder addresses those issues by:

- parsing prompt structure and point requirements
- generating Google Forms as quizzes with answer keys
- splitting large requests into smaller AI batches
- exporting separate `.docx` files for questions and answers
- using per-user Google OAuth on the website
- cleaning temporary generated files after a configurable TTL

## Target audience

This project is mainly intended for:

- school teachers
- private tutors
- test preparation instructors
- curriculum/content creators
- education startups
- admins who prepare quizzes at scale

## Features

- Generate Google Forms quizzes from plain prompts
- Generate Google Forms surveys from plain prompts
- Automatically create answer keys for supported questions
- Set different points for multiple choice and essay questions
- Auto-generate a simple title such as `English - 10 SMK`
- Return both editor and view links for Google Forms
- Generate two Word files:
  - question sheet
  - answer key
- Large Word jobs processed asynchronously with progress polling
- Separate download buttons for each generated Word file
- Temporary job/file expiration with automatic cleanup
- Web UI with Indonesian / English language toggle
- Telegram bot support
- CLI support for local use

## Technology stack

### Backend

- Python
- `http.server` for the lightweight Vercel-compatible HTTP handler
- Google Forms API
- Google Drive / OAuth flow via `google-auth` and `google-auth-oauthlib`
- OpenRouter API for AI generation

### Document generation

- `python-docx` for `.docx` output

### Frontend

- Vanilla HTML
- Vanilla CSS
- Vanilla JavaScript

### Deployment

- Vercel for the website
- Telegram Bot API for chat-based access

## Project structure

- `agent.py` — main quiz generation logic
- `api/index.py` — website entrypoint and Vercel serverless handler
- `google_services.py` — Google Forms and OAuth related logic
- `docx_generator.py` — Word export generation
- `telegram_bot.py` — Telegram bot integration
- `config.py` — environment variable loading
- `vercel.json` — Vercel routing and cron configuration

## Live demo

If the public deployment is active, you can try the website here:

- `https://ai-forms-teach.vercel.app`

If you deploy your own copy, replace that URL with your own Vercel domain.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

## Environment variables

Create a local `.env` file or configure these values in Vercel:

- `OPENROUTER_API_KEY`
- `MODEL_NAME` — optional, default: `openrouter/owl-alpha`
- `TELEGRAM_BOT_TOKEN` — required only for Telegram bot usage
- `GOOGLE_CLIENT_SECRET_JSON`
- `GOOGLE_TOKEN_JSON` — optional for local CLI usage
- `APP_BASE_URL`
- `APP_SECRET`
- `JOB_TTL_SECONDS` — optional, default: `3600`
- `CRON_SECRET`

## Google OAuth setup for the website

For the website, each user signs in with their own Google account.  
That means `GOOGLE_CLIENT_SECRET_JSON` must contain the full JSON content of a **Web application OAuth client**, not a shared user token.

### Steps

1. Open Google Cloud Console.
2. Create an OAuth Client ID with type **Web application**.
3. Add the authorized redirect URI:

```bash
https://your-domain.vercel.app/auth/google/callback
```

4. Copy the full JSON content into `GOOGLE_CLIENT_SECRET_JSON`.
5. Set `APP_BASE_URL`, for example:

```bash
https://your-domain.vercel.app
```

6. Set `APP_SECRET` to a long random secret string.
7. Set `CRON_SECRET` to a long random secret string for scheduled cleanup protection.

## Running locally

### CLI

```bash
python3 agent.py
```

### Telegram bot

```bash
python3 telegram_bot.py
```

### Local web server behavior

This repository is primarily structured for Vercel deployment through `api/index.py`.  
If you want to test the web flow locally, make sure your environment variables and Google OAuth redirect URI are configured correctly for localhost or your local tunnel URL.

## Deploying to Vercel

1. Push the project to GitHub.
2. Import the repository into Vercel.
3. Add all required environment variables.
4. Deploy.

The web page is served from:

- `/`

The generate endpoint is:

- `/api/generate`

## Async jobs, temporary files, and cleanup

Large Word generation requests are processed as async jobs.

Generated job data and Word files are stored temporarily in `/tmp` on the server runtime and are removed after the configured TTL.

### Cleanup behavior

- Expired files are cleaned opportunistically when new requests arrive.
- A scheduled cleanup endpoint is also provided:

```bash
/api/cron/cleanup-jobs
```

- The endpoint is protected with `CRON_SECRET`.

### TTL configuration

```bash
JOB_TTL_SECONDS=3600
```

That means generated files expire after 1 hour by default.

## Vercel cron note

This repository already includes a cron entry in `vercel.json`.

Important limitation:

- On Vercel Hobby, cron runs only once per day.
- If you need cleanup every 30 minutes or every 1 hour, use Vercel Pro and adjust the cron schedule.

## Security notes

- Do not commit `.env`, `credentials.json`, or `token.json` to GitHub.
- Store secrets in environment variables.
- Each website user should authenticate with their own Google account.
- Temporary generated files should expire automatically using TTL cleanup.

## Netlify note

This project’s current backend architecture targets Vercel’s Python runtime directly.  
A static frontend could be hosted elsewhere, but the Python backend in this repo is designed for Vercel deployment.

## Example prompt template

```text
Create questions for grade [GRADE] for the subject [SUBJECT], topic [TOPIC], difficulty [LOW/MEDIUM/HIGH], with [MCQ COUNT] multiple choice questions up to option [D/E] and [ESSAY COUNT] essay questions, with [MCQ POINTS] points for multiple choice and [ESSAY POINTS] points for essay.
```

## License

No license file is included in this repository yet. Add one if you plan to distribute the project publicly under a specific license.
