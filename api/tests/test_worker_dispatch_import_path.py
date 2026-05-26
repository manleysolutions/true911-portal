"""Regression guard for the RQ worker dispatch wiring.

What this protects against
==========================

When the API enqueues a job via :func:`job_service.create_and_enqueue`,
RQ stores a dotted-path string identifying the function the worker
should call when it pops the job (``"worker.dispatch"``).  RQ does
NOT validate that string at enqueue time — it only tries to import
it when the worker pops the job.

If the string is wrong, the worker raises ``ModuleNotFoundError`` on
every pop and the DB ``Job`` row stays at
``status='queued', attempt=0, started_at=NULL`` forever (because
``job_service.mark_running`` is only called from inside ``dispatch``
itself).  This is the exact failure that bit T-Mobile callback ingest
in production after ``FEATURE_TMOBILE_CALLBACK_INGEST=true`` was
flipped on — the IntegrationPayload + Job row landed in Postgres,
but the worker never processed it because RQ had been pointed at
``"app.worker.dispatch"`` (which does not exist; ``worker.py`` lives
at ``api/worker.py``, importable as top-level ``worker``).

These tests pin the contract:

  * Every string ``job_service`` passes to ``q.enqueue`` resolves to
    an importable callable.
  * That callable IS the same ``dispatch`` function the worker
    process executes.
  * The worker subscribes to the ``default`` queue so
    ``webhook.tmobile`` (enqueued there by the T-Mobile callback
    router) is actually visible to the worker.
  * Every ``job_type`` ``job_service`` produces has a handler entry
    in ``worker._HANDLERS`` — including ``webhook.tmobile``.

Future refactor risk
====================

If anyone moves ``worker.py`` (e.g. into ``api/app/worker.py``) or
changes the Render ``startCommand`` (``python worker.py`` from
``rootDir: api``), the string in :func:`job_service._enqueue_rq` must
be updated to match.  These tests will catch the mismatch at PR time.
"""

from __future__ import annotations

import importlib
import inspect
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from app.services import job_service


# ─── Helpers ────────────────────────────────────────────────────────


def _capture_enqueue_string() -> str:
    """Run job_service._enqueue_rq against a fake Redis/Queue and
    return the dotted-path string it passes to ``q.enqueue``.

    Patches the redis + rq imports so no network call is attempted.
    """
    captured: dict[str, str] = {}

    class _FakeQueue:
        def __init__(self, name, connection):
            pass

        def enqueue(self, func_path, *args, **kwargs):
            captured["func_path"] = func_path

        def enqueue_in(self, _delay, func_path, *args, **kwargs):
            captured["func_path"] = func_path

    fake_redis = MagicMock()
    fake_redis.from_url = MagicMock(return_value=MagicMock())

    with patch.dict(
        "sys.modules",
        {
            "redis": MagicMock(Redis=fake_redis),
            "rq": MagicMock(Queue=_FakeQueue),
        },
    ), patch("app.config.settings.REDIS_URL", "redis://fake:6379/0"):
        from app.models.job import Job as _Job

        job = _Job(id=42, job_type="webhook.tmobile", queue="default")
        job_service._enqueue_rq(job)

    return captured.get("func_path", "")


# ─── Enqueue-string contract ────────────────────────────────────────


class TestEnqueueStringResolvesToRealDispatch:
    """The bug-class: a string that doesn't import on the worker side."""

    def test_enqueue_string_is_importable(self):
        """Whatever module:func string job_service passes to RQ must
        be importable from the same Python environment the worker
        runs in — otherwise the job is silently lost."""
        path = _capture_enqueue_string()
        assert path, "job_service._enqueue_rq did not call q.enqueue"

        module_name, _, attr_name = path.partition(".")
        # The string is a flat 'module.attr' (no submodule), which is
        # what the worker.py top-level layout requires.  If a future
        # change introduces 'pkg.module.attr', adjust the partition.
        assert module_name and attr_name, (
            f"Enqueue string {path!r} is not a 'module.attr' form"
        )
        try:
            mod = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:  # pragma: no cover - regression channel
            pytest.fail(
                f"Enqueue string {path!r} points at module {module_name!r} "
                f"which is not importable: {exc}.  This is the root cause "
                f"of stuck status='queued' jobs in production."
            )
        assert hasattr(mod, attr_name), (
            f"Enqueue string {path!r}: module {module_name!r} has no "
            f"attribute {attr_name!r}"
        )

    def test_enqueue_string_resolves_to_the_worker_dispatch_callable(self):
        """Beyond importability, the resolved callable must BE the
        ``worker.dispatch`` function — not a stub, not a same-named
        function in a different module."""
        path = _capture_enqueue_string()
        module_name, _, attr_name = path.partition(".")
        mod = importlib.import_module(module_name)
        resolved = getattr(mod, attr_name)

        worker_module = importlib.import_module("worker")
        assert resolved is worker_module.dispatch, (
            f"Enqueue string {path!r} resolved to {resolved!r}, which is "
            f"NOT worker.dispatch.  The worker will execute the wrong code."
        )

    def test_retry_enqueue_uses_same_string(self):
        """The retry path in ``mark_failed`` re-enqueues via
        ``q.enqueue_in``.  It must use the same correct string — a
        divergence between the two paths would mean the first attempt
        works but every retry silently dies."""
        # Grep the source so we catch hard-coded literals (including
        # the comment-only documentation that the two paths must match).
        src = inspect.getsource(job_service)
        # Exactly two occurrences as quoted literal: one in
        # _enqueue_rq, one in mark_failed.
        assert src.count('"worker.dispatch"') == 2, (
            "Expected exactly two occurrences of \"worker.dispatch\" "
            "in job_service.py (initial enqueue + retry).  Found "
            f"{src.count(chr(34) + 'worker.dispatch' + chr(34))}.  If a "
            "refactor centralised the string into a constant, update "
            "this guard to match."
        )
        # And the historically-wrong string must not reappear.
        assert '"app.worker.dispatch"' not in src, (
            "job_service.py contains the historically-wrong "
            '"app.worker.dispatch" string.  This is the bug that left '
            "T-Mobile callback jobs stuck at status='queued'."
        )


# ─── Worker queue subscription ──────────────────────────────────────


class TestWorkerQueueSubscription:
    """The worker must subscribe to the queue ``webhook.tmobile`` is
    enqueued to (currently ``default``)."""

    def test_worker_subscribes_to_default_queue(self):
        """Read worker.py source and assert ``default`` is in the
        startup queue list.  A subprocess-level check would be more
        thorough but this catches the obvious regression."""
        worker_src = (
            pathlib.Path(__file__).resolve().parents[1] / "worker.py"
        ).read_text(encoding="utf-8")
        assert '"default"' in worker_src, (
            "worker.py no longer subscribes to the 'default' queue — "
            "webhook.tmobile jobs (enqueued there by the T-Mobile "
            "callback router) will not be popped."
        )

    def test_tmobile_callback_router_enqueues_to_default_queue(self):
        """The router-side default queue selection must match the
        worker's subscription list."""
        router_src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "app" / "routers" / "tmobile_callback.py"
        ).read_text(encoding="utf-8")
        assert 'queue="default"' in router_src, (
            "T-Mobile callback router no longer enqueues to the 'default' "
            "queue.  Either update worker.py's subscription list or revert."
        )


# ─── Handler registry ───────────────────────────────────────────────


class TestHandlerRegistry:
    """Every job_type the worker is asked to process must have an
    entry in ``worker._HANDLERS`` — otherwise dispatch marks the job
    failed with 'Unknown job type'."""

    def test_webhook_tmobile_registered(self):
        worker = importlib.import_module("worker")
        assert "webhook.tmobile" in worker._HANDLERS, (
            "worker._HANDLERS missing 'webhook.tmobile' — the T-Mobile "
            "callback worker job will be rejected as unknown."
        )

    def test_webhook_tmobile_handler_resolves(self):
        """The handler string in _HANDLERS must be importable to the
        real callable.  Catches a rename of sim_service.handle_webhook
        without updating the registry."""
        worker = importlib.import_module("worker")
        handler_path = worker._HANDLERS["webhook.tmobile"]
        module_name, _, func_name = handler_path.rpartition(":")
        mod = importlib.import_module(module_name)
        handler = getattr(mod, func_name, None)
        assert callable(handler), (
            f"_HANDLERS['webhook.tmobile'] = {handler_path!r} did not "
            f"resolve to a callable.  Check sim_service.handle_webhook."
        )

    def test_all_handlers_resolve_at_import_time(self):
        """Defensive: every handler in the registry must import.  A
        bad path silently breaks the relevant job_type only when a
        job of that type happens to land in production."""
        worker = importlib.import_module("worker")
        broken: list[str] = []
        for job_type, handler_path in worker._HANDLERS.items():
            module_name, _, func_name = handler_path.rpartition(":")
            try:
                mod = importlib.import_module(module_name)
            except Exception as exc:
                broken.append(f"{job_type}={handler_path!r} ({exc})")
                continue
            if not callable(getattr(mod, func_name, None)):
                broken.append(f"{job_type}={handler_path!r} (not callable)")
        assert not broken, (
            f"Unresolvable handlers in worker._HANDLERS: {broken}"
        )


# ─── Dispatch behavior — unknown job, handler failure ──────────────


class TestDispatchSafety:
    """End-to-end exercise of ``worker._dispatch_async`` with mocks
    for the DB session.  Proves:

      * Unknown job_type → ``mark_failed`` with a descriptive error
      * Handler raises  → exception is captured, job marked failed,
                          DB committed
      * Handler succeeds → ``mark_completed`` with the handler result

    The user's prod-stuck job had attempt=0, started_at=NULL because
    dispatch was never called at all (RQ failed to import the
    function).  These tests prove that once dispatch DOES run, no
    other code path can silently leave a job stuck.
    """

    @pytest.mark.asyncio
    async def test_unknown_job_type_is_marked_failed(self):
        import worker
        from app.models.job import Job as _Job

        fake_job = _Job(id=99, job_type="bogus.unknown", payload={})

        with patch("worker.AsyncSessionLocal", create=True) as _ss:
            async_ctx = MagicMock()
            db = MagicMock()
            db.commit = _AsyncNoop()
            async_ctx.__aenter__ = _AsyncReturn(db)
            async_ctx.__aexit__ = _AsyncReturn(None)
            _ss.return_value = async_ctx

            with patch(
                "app.database.AsyncSessionLocal",
                _ss,
                create=True,
            ), patch(
                "app.services.job_service.mark_running",
                new=_AsyncReturn(fake_job),
            ), patch(
                "app.services.job_service.mark_failed",
                new=_AsyncRecorder(),
            ) as failed_recorder:
                await worker._dispatch_async(99)

        assert failed_recorder.calls, "mark_failed was not called"
        # Second positional arg is the error message
        err_msg = failed_recorder.calls[0][0][2]
        assert "Unknown job type" in err_msg
        assert "bogus.unknown" in err_msg

    @pytest.mark.asyncio
    async def test_handler_exception_is_marked_failed(self):
        import worker
        from app.models.job import Job as _Job

        fake_job = _Job(id=100, job_type="webhook.tmobile", payload={})

        async def _boom(_db, _job):
            raise RuntimeError("simulated processor crash")

        async_ctx = MagicMock()
        db = MagicMock()
        db.commit = _AsyncNoop()
        async_ctx.__aenter__ = _AsyncReturn(db)
        async_ctx.__aexit__ = _AsyncReturn(None)

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=async_ctx,
            create=True,
        ), patch(
            "app.services.job_service.mark_running",
            new=_AsyncReturn(fake_job),
        ), patch(
            "app.services.job_service.mark_failed",
            new=_AsyncRecorder(),
        ) as failed_recorder, patch.object(
            worker, "_import_handler", return_value=_boom,
        ):
            await worker._dispatch_async(100)

        assert failed_recorder.calls, "mark_failed was not called"
        err_msg = failed_recorder.calls[0][0][2]
        assert "simulated processor crash" in err_msg

    @pytest.mark.asyncio
    async def test_handler_success_is_marked_completed(self):
        import worker
        from app.models.job import Job as _Job

        fake_job = _Job(id=101, job_type="webhook.tmobile", payload={})

        async def _ok(_db, _job):
            return {"payload_id": "wh-x", "processed": True}

        async_ctx = MagicMock()
        db = MagicMock()
        db.commit = _AsyncNoop()
        async_ctx.__aenter__ = _AsyncReturn(db)
        async_ctx.__aexit__ = _AsyncReturn(None)

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=async_ctx,
            create=True,
        ), patch(
            "app.services.job_service.mark_running",
            new=_AsyncReturn(fake_job),
        ), patch(
            "app.services.job_service.mark_completed",
            new=_AsyncRecorder(),
        ) as completed_recorder, patch.object(
            worker, "_import_handler", return_value=_ok,
        ):
            await worker._dispatch_async(101)

        assert completed_recorder.calls
        result = completed_recorder.calls[0][0][2]
        assert result == {"payload_id": "wh-x", "processed": True}


# ─── async-aware MagicMock helpers (avoid depending on
#     unittest.mock.AsyncMock kwarg quirks) ──────────────────────────


class _AsyncNoop:
    def __call__(self, *a, **k):
        async def _():
            return None
        return _()


class _AsyncReturn:
    def __init__(self, value):
        self.value = value

    def __call__(self, *a, **k):
        value = self.value
        async def _():
            return value
        return _()


class _AsyncRecorder:
    def __init__(self):
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *a, **k):
        self.calls.append((a, k))
        async def _():
            return None
        return _()
