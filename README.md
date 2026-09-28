# AIwithRC-RAG

Upload documents, ask questions, and get answers that cite the exact passage they came from.
Self-hosted, MIT licensed, runs on a laptop or a small VPS (2–4 GB RAM, no GPU).

> **Status: phase 1 of 6 (skeleton).** Sign-up, sign-in, sessions, profile, theme and the app shell work.
> Document upload, answering, sharing and the activity log arrive in the next phases (see [Roadmap](#roadmap)).

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
2. **Ingest:** knowledge bases, uploads, parsing, chunking, local embeddings, live indexing status
3. **Ask:** provider connections, hybrid retrieval + rerank, streaming cited answers, source panel
4. **Hook:** drop-to-answer first run, suggested questions, shareable public answers
5. **History, Settings, Profile:** activity log, CSV export, workspace settings, re-index
6. **Harden and ship:** tests, mobile pass, VPS guide, screenshots

## License

[MIT](LICENSE). The bundled Geist fonts are under the SIL Open Font License (`web/public/fonts/OFL-LICENSE.txt`).
