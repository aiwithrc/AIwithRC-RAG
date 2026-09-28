# Contributing

Thanks for helping. A few ground rules keep the project small and easy to self-host.

## Setup

See [README → Local development](README.md#local-development).

## Before opening a PR

- `cd api && uv run pytest`
- `cd web && npm run typecheck && npm test`
- Schema change? Add an Alembic migration (`uv run alembic revision --autogenerate -m "..."`), review it,
  and make sure `uv run alembic check` reports no drift.

## Guidelines

- **The prototype is the UI spec.** `design/AIwithRC-RAG.dc.html` defines layout, copy and states.
  Match it; if you think it's wrong, open an issue first.
- **Colours and fonts come from tokens only** (`web/src/styles/tokens.css`). No hex values in components.
- **Licences:** MIT-compatible dependencies only. No GPL/AGPL (e.g. no PyMuPDF). Propose new dependencies
  in an issue before adding them.
- **Keep it one process.** No Redis, Celery or separate DB server. Background work goes through the `jobs` table.
- **Log user-visible actions** with `app.services.events.record()` so they show up in History.
- Commits: short imperative subject line, explain the *why* in the body.
