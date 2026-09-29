# AIwithRC-RAG

Upload documents, ask questions, and get answers that cite the exact passage they came from.
Self-hosted, MIT licensed, runs on a laptop or a small VPS (2–4 GB RAM, no GPU).

> **Status: phase 2 of 6 (ingest).** Sign-in, profile, model provider connections, knowledge bases and
> document upload with live indexing work. Answering, sharing and the activity log arrive in the next phases
> (see [Roadmap](#roadmap)).

## Quick start (Docker)

```bash
cp .env.example .env        # then set APP_SECRET to a long random value
docker compose up --build
```

Open <http://localhost:8000>. The first account you create becomes the workspace owner.
After that, sign-up is closed unless you set `ALLOW_SIGNUP=true`.

Everything the app stores (SQLite database, vectors, uploads, model cache) lives in `./data`.
Back up that folder and you have backed up everything.

## Local development

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
# API on :8000
cd api
uv sync
uv run python -m uvicorn app.main:app --reload --port 8000

# Web on :5173 (proxies /api to :8000)
cd web
npm install
npm run dev
```

Open <http://localhost:5173>. Without the Vite dev server, `npm run build` in `web/` and FastAPI serves the
built app from <http://localhost:8000>.

### Tests

```bash
cd api && uv run pytest
cd web && npm test && npm run typecheck
```

### Admin CLI

```bash
cd api
uv run python -m app.cli create-user --email you@example.com --name "Your Name"
uv run python -m app.cli reset-password --email you@example.com
```

In Docker: `docker compose exec app python -m app.cli reset-password --email you@example.com`.
Resetting a password also signs that user out everywhere. This is the v1 answer to "Forgot password?".

## Connecting a model

Open **API keys** and add a connection. Any OpenAI-compatible API works; Anthropic is supported natively.

| Provider | API Base (app running in Docker) | API Key |
|---|---|---|
| LM Studio on your computer | `http://host.docker.internal:1234/v1` | leave empty |
| Ollama on your computer | `http://host.docker.internal:11434/v1` | leave empty |
| OpenAI | `https://api.openai.com/v1` | `sk-…` |
| Anthropic | `https://api.anthropic.com/v1` | `sk-ant-…` |
| OpenRouter | `https://openrouter.ai/api/v1` | `sk-or-…` |

Running the API outside Docker? Use `http://localhost:…` instead of `host.docker.internal`.

## Documents and indexing

Upload PDF, DOCX, MD, TXT, CSV or XLSX files (50 MB each by default) on a knowledge base's page, or drop one
on the empty chat screen. Each file is parsed (PDFs keep page numbers, Word and Markdown keep their headings),
split into ~800-token passages along sentence boundaries, embedded **on this server** with
`BAAI/bge-small-en-v1.5`, and stored in Chroma (vectors) and SQLite FTS5 (keywords). The Docker image ships
with the embedding model, so indexing works without internet access.

Scanned PDFs have no text layer and fail with "No text layer found. Turn on OCR in Settings." OCR is optional:
install [OCRmyPDF](https://ocrmypdf.readthedocs.io/) with Tesseract on the server and turn on OCR in Settings.

## Configuration

All settings are environment variables; see [`.env.example`](.env.example) for the full list.

| Variable | Default | What it does |
|---|---|---|
| `APP_SECRET` | *(insecure default)* | Encrypts stored provider API keys. **Set it, and don't change it later.** |
| `DATA_DIR` | `./data` (`/data` in Docker) | Database, vectors, uploads, model cache |
| `ALLOW_SIGNUP` | `false` | Allow sign-ups after the first (owner) account |
| `PUBLIC_URL` | `http://localhost:8000` | Used in share links and the login footer |
| `COOKIE_SECURE` | `false` | Set `true` when serving over HTTPS |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | IPs of reverse proxies whose `X-Forwarded-For` is trusted |

## Security notes

- Passwords are hashed with Argon2. Sessions are server-side; the browser only holds an opaque
  httpOnly, SameSite=Lax cookie.
- Every mutating API request must send an `X-Requested-With` header (CSRF defence on top of SameSite).
- Sign-in is rate-limited to 5 failed attempts per 15 minutes per IP and per email. Failed attempts
  are logged as "Blocked" events.
- Provider API keys are encrypted at rest (Fernet, key derived from `APP_SECRET`) and never returned by the API.

## Project layout

```
api/     FastAPI app (app/), Alembic migrations, tests
web/     React + TypeScript + Vite front end
design/  Clickable prototype, the source of truth for the UI (open AIwithRC-RAG.dc.html)
```

## Roadmap

1. **Skeleton** ✅ auth, sessions, app shell, light/dark theme, Docker
2. **Ingest** ✅ knowledge bases, uploads, parsing, chunking, local embeddings, live indexing status
3. **Ask:** provider connections, hybrid retrieval + rerank, streaming cited answers, source panel
4. **Hook:** drop-to-answer first run, suggested questions, shareable public answers
5. **History, Settings, Profile:** activity log, CSV export, workspace settings, re-index
6. **Harden and ship:** tests, mobile pass, VPS guide, screenshots

## License

[MIT](LICENSE). The bundled Geist fonts are under the SIL Open Font License (`web/public/fonts/OFL-LICENSE.txt`).
