"""The `jobs` table as a queue. Restart-safe: jobs left `running` by a crash are re-queued on startup."""

import json
import logging
import traceback
from collections.abc import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.db import SessionLocal, utcnow
from app.models import Document, Job

log = logging.getLogger("aiwithrc.jobs")

Handler = Callable[[dict], None]
_handlers: dict[str, Handler] = {}
_notify: Callable[[], None] = lambda: None  # set by the worker when it's running


def handler(job_type: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        _handlers[job_type] = fn
        return fn

    return register


def set_notifier(fn: Callable[[], None]) -> None:
    global _notify
    _notify = fn


def enqueue(db: DbSession, job_type: str, payload: dict) -> Job:
    """Add a job. Commit the session, then the worker picks it up right away."""
    job = Job(type=job_type, payload_json=json.dumps(payload))
    db.add(job)
    return job


def notify() -> None:
    _notify()


def requeue_stale() -> int:
    """After a restart, anything that was mid-flight goes back in the queue."""
    with SessionLocal() as db:
        n = db.execute(
            update(Job).where(Job.status == "running").values(status="queued", started_at=None)
        ).rowcount
        db.execute(
            update(Document)
            .where(Document.status.in_(["parsing", "chunking", "embedding"]))
            .values(status="queued", progress=0)
        )
        db.commit()
        return n or 0


def claim_next() -> Job | None:
    with SessionLocal() as db:
        job = db.scalars(select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)).first()
        if job is None:
            return None
        claimed = db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "queued")
            .values(status="running", started_at=utcnow(), attempts=Job.attempts + 1)
        ).rowcount
        db.commit()
        if not claimed:  # lost a race; try again next tick
            return None
        db.refresh(job)
        return job


def execute(job: Job) -> None:
    fn = _handlers.get(job.type)
    status, error = "done", None
    try:
        if fn is None:
            raise RuntimeError(f"No handler for job type {job.type!r}")
        fn(json.loads(job.payload_json or "{}"))
    except Exception as e:  # handlers turn expected failures into document status; this is the safety net
        log.exception("Job %s (%s) failed", job.id, job.type)
        status, error = "failed", "".join(traceback.format_exception_only(e)).strip()[:2000]
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.id == job.id).values(status=status, error=error, finished_at=utcnow()))
        db.commit()


def process_all(max_jobs: int = 1000) -> int:
    """Run queued jobs synchronously until the queue is empty (tests and the CLI)."""
    n = 0
    while n < max_jobs and (job := claim_next()) is not None:
        execute(job)
        n += 1
    return n
