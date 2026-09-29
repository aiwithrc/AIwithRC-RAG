"""In-process background worker: one asyncio task that runs jobs one at a time in a thread.

One job at a time keeps memory predictable on a 2 GB VPS (the embedding model is the big user).
"""

import asyncio
import contextlib
import logging

from app.jobs import queue

log = logging.getLogger("aiwithrc.jobs")

POLL_SECONDS = 2.0


class Worker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        queue.set_notifier(self.notify)
        self._task = asyncio.create_task(self._run(), name="job-worker")

    async def stop(self) -> None:
        queue.set_notifier(lambda: None)
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def notify(self) -> None:
        """Thread-safe: wake the worker now instead of at the next poll."""
        if self._loop and self._wake and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._wake.set)

    async def _run(self) -> None:
        assert self._wake is not None
        n = await asyncio.to_thread(queue.requeue_stale)
        if n:
            log.info("Re-queued %d interrupted job(s)", n)
        asyncio.create_task(self._warm_up())
        while True:
            try:
                job = await asyncio.to_thread(queue.claim_next)
            except Exception:
                log.exception("Could not read the job queue")
                job = None
            if job is None:
                self._wake.clear()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), POLL_SECONDS)
                continue
            await asyncio.to_thread(queue.execute, job)

    async def _warm_up(self) -> None:
        """Load the embedding model in the background so the first upload doesn't wait for it."""
        from app.rag.embed import get_embedder

        try:
            await asyncio.to_thread(lambda: get_embedder().dim)
        except Exception:
            log.warning("Embedding model not loaded yet; it will load on the first upload.", exc_info=True)


worker = Worker()
