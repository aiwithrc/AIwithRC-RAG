"""FastAPI application: JSON API under /api, built SPA from /."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_engine
from app.migrate import upgrade_to_head
from app.jobs import ingest  # noqa: F401  (registers the ingest job handler)
from app.jobs.worker import worker
from app.routers import auth, chats, connections, documents, kbs, me, settings as settings_router

log = logging.getLogger("aiwithrc")

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(*, run_migrations: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        settings.ensure_dirs()
        init_engine(settings.db_url)
        if run_migrations:
            upgrade_to_head(settings.db_url)
        if settings.app_secret == "change-me-in-production":
            log.warning("APP_SECRET is the default value. Set it in .env before exposing this server.")
        if settings.start_worker:
            worker.start()
        try:
            yield
        finally:
            if settings.start_worker:
                await worker.stop()

    app = FastAPI(title="AIwithRC-RAG", version="0.1.0", lifespan=lifespan, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None)

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # SameSite=Lax blocks most cross-site POSTs; this header check covers the rest
        # (a plain HTML form can't set custom headers).
        path = request.url.path
        if request.method in _MUTATING and path.startswith("/api/") and not request.headers.get("x-requested-with"):
            return JSONResponse({"detail": "Missing X-Requested-With header."}, status_code=403)
        return await call_next(request)

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": app.version}

    api.include_router(auth.router)
    api.include_router(me.router)
    api.include_router(kbs.router)
    api.include_router(documents.router)
    api.include_router(connections.router)
    api.include_router(chats.router)
    api.include_router(settings_router.router)
    app.include_router(api)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_not_found(rest: str) -> JSONResponse:
        return JSONResponse({"detail": "Not found"}, status_code=404)

    _mount_spa(app, settings.web_dist)
    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.exists():
        return
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    if (dist / "fonts").exists():
        app.mount("/fonts", StaticFiles(directory=dist / "fonts"), name="fonts")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
