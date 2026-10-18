"""web/jobs.py — P18.3: persisted background job manager + streaming.

Why this exists
---------------
Before P18.3, the long commands (``backfill``, ``backtest``, ``simulator``,
``derivatives collect``, ``cross collect``) ran inside **one blocking POST**
behind a timeout. Three failures followed:

1. **A browser close killed the job.** The work lived inside the request, so
   navigating away (or the 900s timeout firing) abandoned a half-done backfill.
2. **A duplicate click started a duplicate run.** Nothing stopped two tabs
   from backfilling the same series at once.
3. **Progress was invisible.** The client saw "working…" until the whole run
   returned or timed out.

This module moves those jobs behind a **persisted queue** with status,
progress, cancel and an append-only log. The job runs in the server process
(not in the request), so closing the browser does not kill it; the state is
written to the signal database, so a reconnect or even a server restart never
loses the *record* of the run — the client resumes from the last persisted
state instead of starting over.

Safety model
------------
* **Allow-list only.** A job kind must be declared in :data:`JOB_KINDS` and is
  executed as ``python main.py <argv>`` with the exact arguments ``web/
  command_center.build_argv`` validates — never a shell string, never a free
  command. No catalog entry can place an exchange order (SKY has no trading
  key); the paper runner is simulation-only.
* **Natural deduplication.** ``params_hash = sha256(kind + canonical
  params)``. Submitting the same job while an identical one is still
  ``queued``/``running`` returns the existing job instead of starting a
  second run. (The v1 endpoint additionally reuses ``IdempotencyStore`` for
  the request-level retry, per the P18.2 contract.)
* **One worker, one job at a time.** Long jobs are heavy and share the same
  Parquet store and SQLite DB; running several at once would just thrash.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import config

ROOT = Path(__file__).resolve().parent.parent

# ── job kinds (the allow-list) ───────────────────────────────────────────
#: Every runnable job kind. ``argv`` is the ``python main.py`` argument list
#: the worker executes; ``steps`` (optional) expands a composite job into a
#: sequence of child jobs run in order, each reporting its own phase and
#: progress. ``inputs`` describe the validated parameters a submitter may
#: pass; validation is delegated to ``web.command_center.build_argv`` so the
#: browser Command Center and the job queue share one allow-list.
JOB_KINDS: dict[str, dict] = {
    "backfill": {
        "title": "Backfill history",
        "argv": ["backfill"],
        "what": "Download paginated candle history into the local Parquet store.",
        "inputs": [
            {
                "name": "symbol",
                "label": "Asset",
                "type": "text",
                "default": "BTCUSDT",
                "flag": "--symbol",
            },
            {
                "name": "tf",
                "label": "Timeframe",
                "type": "choice",
                "options": ["1m", "5m", "15m", "1h", "4h", "1d"],
                "default": "1m",
                "flag": "--tf",
            },
            {
                "name": "market",
                "label": "Market",
                "type": "choice",
                "options": ["spot", "perp"],
                "default": "perp",
                "flag": "--market",
            },
            {
                "name": "since",
                "label": "Since",
                "type": "text",
                "default": "30d",
                "flag": "--since",
            },
        ],
    },
    "backtest": {
        "title": "Backtest",
        "argv": ["backtest"],
        "what": "Walk-forward grade of the engine's plans over stored history.",
        "inputs": [
            {
                "name": "symbol",
                "label": "Asset",
                "type": "text",
                "default": "BTCUSDT",
                "flag": "--symbol",
            },
            {
                "name": "tf",
                "label": "Timeframe",
                "type": "choice",
                "options": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"],
                "default": "15m",
                "flag": "--tf",
            },
            {
                "name": "bars",
                "label": "Bars",
                "type": "int",
                "default": 500,
                "flag": "--bars",
            },
        ],
    },
    "simulator": {
        "title": "Simulator",
        "argv": ["simulator"],
        "what": "Grind unique backtest and paper samples per setup toward the "
        "100/20 evidence bar (simulator rows never count as live evidence).",
        "inputs": [
            {
                "name": "rounds",
                "label": "Rounds",
                "type": "int",
                "default": 3,
                "flag": "--rounds",
            },
            {
                "name": "symbols",
                "label": "Assets",
                "type": "text",
                "default": "",
                "flag": "--symbols",
            },
            {
                "name": "tf",
                "label": "Timeframe",
                "type": "choice",
                "options": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"],
                "default": "15m",
                "flag": "--tf",
            },
        ],
    },
    "scorecard": {
        "title": "Scorecard",
        "argv": ["scorecard"],
        "what": "Strategy scorecard net of costs, by setup / regime / side / session.",
        "inputs": [
            {
                "name": "source",
                "label": "Book",
                "type": "choice",
                "options": ["db", "backtest", "paper", "store"],
                "default": "db",
                "flag": "--source",
            },
        ],
    },
    "derivatives_collect": {
        "title": "Collect derivatives",
        "argv": ["derivatives", "collect"],
        "what": "Collect funding, open interest, mark, index and basis history.",
        "inputs": [
            {
                "name": "symbol",
                "label": "Asset",
                "type": "text",
                "default": "BTCUSDT",
                "flag": "--symbol",
            },
        ],
    },
    "cross_collect": {
        "title": "Collect cross-exchange",
        "argv": ["cross", "collect"],
        "what": "Collect premium/discount and funding spread across venues.",
        "inputs": [
            {
                "name": "symbol",
                "label": "Asset",
                "type": "text",
                "default": "BTCUSDT",
                "flag": "--symbol",
            },
        ],
    },
}

#: Composite jobs: a single submission that runs a fixed sequence of the
#: allow-listed kinds in order. This is the backbone of the W1 "Build my
#: evidence" flow (Backfill → Backtest → Simulator → Scorecard).
COMPOSITE_JOBS: dict[str, dict] = {
    "evidence": {
        "title": "Build my evidence",
        "what": "One guided run: Backfill → Backtest → Simulator → Scorecard, "
        "streamed with live progress.",
        # W1: these are deliberately closed/validated inputs, not arbitrary
        # command arguments.  The selected asset/timeframe flow into every
        # applicable child step so the four-stage run measures one coherent
        # series rather than silently mixing defaults.
        "inputs": [
            {"name": "symbol", "label": "Asset", "type": "text", "default": "BTCUSDT"},
            {
                "name": "tf",
                "label": "Timeframe",
                "type": "choice",
                "options": ["1m", "5m", "15m", "1h", "4h", "1d"],
                "default": "15m",
            },
            {
                "name": "market",
                "label": "Market",
                "type": "choice",
                "options": ["spot", "perp"],
                "default": "spot",
            },
            {
                "name": "since",
                "label": "History",
                "type": "choice",
                "options": ["7d", "30d", "90d", "180d", "365d"],
                "default": "30d",
            },
            {
                "name": "bars",
                "label": "Backtest bars",
                "type": "int",
                "default": 500,
                "max": 100_000,
            },
            {
                "name": "rounds",
                "label": "Simulator rounds",
                "type": "int",
                "default": 3,
                "max": 1_000,
            },
        ],
        "steps": [
            {"kind": "backfill", "params_from": ["symbol", "tf", "market", "since"]},
            {"kind": "backtest", "params_from": ["symbol", "tf", "bars"]},
            {
                "kind": "simulator",
                "params_map": {"symbol": "symbols", "tf": "tf", "rounds": "rounds"},
            },
            {"kind": "scorecard", "params": {"source": "db"}},
        ],
    },
}

#: Terminal states — the worker stops, and SSE streams emit a final event.
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
#: States that block a duplicate submission (natural dedup window).
LIVE = {"queued", "running"}

STATUS_LABELS = {
    "queued": "queued",
    "running": "running",
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
    "interrupted": "interrupted",
}


class JobError(ValueError):
    """A job submission was refused (unknown kind / bad params / not cancelable)."""


def params_hash(kind: str, params: dict) -> str:
    """Stable dedup fingerprint of a job: kind + canonical params."""
    try:
        canonical = json.dumps(params, sort_keys=True, default=str)
    except Exception:
        canonical = repr(params)
    return hashlib.sha256(f"{kind}\n{canonical}".encode()).hexdigest()


def _coerce_param(spec: dict, raw: Any) -> Any:
    """Mirror ``command_center._coerce`` so job submission validates exactly
    like the browser Command Center does (one allow-list, one validator)."""
    kind = spec.get("type", "text")
    if kind == "int":
        if raw in (None, "", []):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise JobError(f"{spec['name']} must be a whole number")
    if kind == "choice":
        text = str(raw or "").strip()
        options = spec.get("options") or []
        if text and options and text not in options:
            raise JobError(f"{spec['name']} must be one of: {', '.join(options)}")
        return text or (spec.get("default") or "")
    text = str(raw if raw is not None else "").strip()
    if "\n" in text:
        raise JobError(f"{spec['name']} must be a single line")
    return text


def _validated_params(spec: dict, params: dict | None) -> dict:
    """Return only declared, coerced parameters for a job specification."""
    params = params or {}
    allowed = {field["name"] for field in spec.get("inputs", [])}
    unknown = sorted(set(params) - allowed)
    if unknown:
        raise JobError("unknown parameter(s): " + ", ".join(unknown))
    values = {}
    for field in spec.get("inputs", []):
        value = _coerce_param(field, params.get(field["name"], field.get("default")))
        if field.get("type") == "int" and value is not None:
            if value < 1:
                raise JobError(f"{field['name']} must be at least 1")
            # Browser jobs must remain bounded. This is an operational limit,
            # not a trading threshold, and prevents an accidental huge click.
            if value > int(field.get("max", 100_000)):
                raise JobError(f"{field['name']} is too large")
        values[field["name"]] = value
    return values


def build_argv(kind: str, params: dict | None) -> list[str]:
    """Translate a job kind + params into a validated ``main.py`` argv list.

    Raises :class:`JobError` on an unknown kind or invalid parameter, so a
    submitted job is always runnable before it is persisted.
    """
    spec = JOB_KINDS.get(kind)
    if spec is None:
        raise JobError(f"unknown job kind: {kind}")
    values = _validated_params(spec, params)
    argv = list(spec["argv"])
    for field in spec.get("inputs", []):
        value = values.get(field["name"])
        if value in (None, ""):
            continue
        argv.extend([field["flag"], str(value)])
    return argv


def validate_composite(kind: str, params: dict | None) -> dict:
    """Validate and normalize a composite job's public inputs.

    Every expanded child is also checked before the parent row is persisted,
    so a bad mapping can never leave a job stuck in ``running``.
    """
    spec = COMPOSITE_JOBS.get(kind)
    if spec is None:
        raise JobError(f"unknown composite job: {kind}")
    values = _validated_params(spec, params)
    for step in spec.get("steps", []):
        child = dict(step.get("params") or {})
        for name in step.get("params_from") or []:
            child[name] = values.get(name)
        for source, target in (step.get("params_map") or {}).items():
            child[target] = values.get(source)
        build_argv(step["kind"], child)
    return values


def _job_row_to_payload(row: dict) -> dict:
    """A DB row → the client-facing job shape (metadata, not the full log)."""
    try:
        params = json.loads(row.get("params_json") or "{}")
    except Exception:
        params = {}
    return {
        "job_id": row["job_id"],
        "kind": row["kind"],
        "title": (JOB_KINDS.get(row["kind"]) or COMPOSITE_JOBS.get(row["kind"]) or {}).get(
            "title", row["kind"]
        ),
        "params": params,
        "status": row["status"],
        "user": row.get("username"),
        "created_ts": row.get("created_ts"),
        "started_ts": row.get("started_ts"),
        "finished_ts": row.get("finished_ts"),
        "step_index": row.get("step_index", 0),
        "step_total": row.get("step_total", 1),
        "phase": row.get("phase"),
        "exit_code": row.get("exit_code"),
        "error": row.get("error"),
        "cancel_requested": bool(row.get("cancel_requested")),
    }


class JobManager:
    """Persisted background-job queue with a single in-process worker.

    Thread-safety: every DB access opens its own ``SignalDB`` connection
    (WAL + busy_timeout), so the worker thread and Flask request threads can
    read/write the ``jobs`` table concurrently. The full log is appended to a
    per-job file; only the tail is loaded into memory for status/SSE.
    """

    def __init__(
        self,
        db_path: str | None = None,
        log_dir: str | Path | None = None,
        runner: Callable[..., int] | None = None,
    ):
        self.db_path = db_path or config.DB_PATH
        self.log_dir = Path(log_dir) if log_dir else (Path(self.db_path).parent / "job_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        #: Injectable subprocess runner — tests replace this with a fake that
        #: streams a few lines and returns an exit code without a real shell.
        self._runner = runner or self._default_runner
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()
        self._lock = threading.Lock()

    # ── db helpers ───────────────────────────────────────────────────────
    def _db(self):
        from data.database import SignalDB

        return SignalDB(self.db_path) if self.db_path else SignalDB()

    def _log_file(self, job_id: str) -> Path:
        return self.log_dir / f"{job_id}.log"

    # ── submission ───────────────────────────────────────────────────────
    def submit(self, kind: str, params: dict | None = None, user: dict | None = None) -> dict:
        """Validate, dedup and enqueue a job. Returns ``{job_id, created}``.

        ``created`` is False when an identical job is already queued/running —
        the caller should surface the existing run, not start a duplicate.
        """
        params = dict(params or {})
        if kind not in JOB_KINDS and kind not in COMPOSITE_JOBS:
            raise JobError(f"unknown job kind: {kind}")
        # Validate now (before persisting) so a bad job is never enqueued.
        # Composite values are normalized too: ``{}`` and an explicit set of
        # defaults deduplicate as the same guided run.
        if kind in JOB_KINDS:
            build_argv(kind, params)
        else:
            params = validate_composite(kind, params)
        fingerprint = params_hash(kind, params)
        job_id = uuid.uuid4().hex[:16]
        username = (user or {}).get("username")
        user_id = (user or {}).get("id")
        step_total = len(COMPOSITE_JOBS[kind]["steps"]) if kind in COMPOSITE_JOBS else 1
        now = int(time.time() * 1000)
        log_path = str(self._log_file(job_id))

        with self._db() as db:
            # Natural dedup: an identical live job means this click is a
            # repeat — hand back the existing run instead of starting another.
            existing = db.conn.execute(
                "SELECT job_id FROM jobs WHERE params_hash=? AND status IN "
                "('queued','running') ORDER BY created_ts DESC LIMIT 1",
                (fingerprint,),
            ).fetchone()
            if existing is not None:
                return {"job_id": existing["job_id"], "created": False}
            db.conn.execute(
                "INSERT INTO jobs(job_id, kind, params_json, params_hash, status, "
                "user_id, username, created_ts, step_index, step_total, phase, "
                "log_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    kind,
                    json.dumps(params, default=str),
                    fingerprint,
                    "queued",
                    user_id,
                    username,
                    now,
                    0,
                    step_total,
                    "queued",
                    log_path,
                ),
            )
            db.conn.commit()
        self._wake.set()
        self.start()
        return {"job_id": job_id, "created": True}

    def get(self, job_id: str, tail_lines: int = 200) -> dict | None:
        """One job's persisted state plus a tail of its log."""
        with self._db() as db:
            row = db.conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                return None
            payload = _job_row_to_payload(dict(row))
        payload["log_tail"] = self.tail(job_id, tail_lines)
        payload["log_full"] = str(self._log_file(job_id))
        return payload

    def list_jobs(self, limit: int = 50, status: str | None = None) -> list[dict]:
        """Recent jobs, newest first, optionally filtered by status."""
        q = "SELECT * FROM jobs"
        args: tuple = ()
        if status:
            q += " WHERE status=?"
            args = (status,)
        q += " ORDER BY created_ts DESC LIMIT ?"
        args = (*args, int(limit))
        with self._db() as db:
            rows = db.conn.execute(q, args).fetchall()
        return [_job_row_to_payload(dict(r)) for r in rows]

    def tail(self, job_id: str, n: int = 200) -> str:
        """Last ``n`` lines of the job log, newest last."""
        path = self._log_file(job_id)
        try:
            data = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        lines = data.splitlines()
        return "\n".join(lines[-n:])

    def evidence_guidance(self, by_setup: list[dict]) -> dict:
        """Honest W1 result and rough simulator-round projection.

        The estimate uses additions printed by completed simulator/evidence
        jobs. It is explicitly aggregate and approximate: deduplication can
        slow future rounds and aggregate additions may include non-primary
        setups. If no observed pace exists we say ``unknown`` rather than
        inventing a percentage.
        """
        primary = [s for s in (by_setup or []) if s.get("primary", True)]
        bt_gap = sum(
            max(0, int(s.get("backtest_target") or 0) - int(s.get("backtest_n") or 0))
            for s in primary
        )
        pp_gap = sum(
            max(0, int(s.get("paper_target") or 0) - int(s.get("paper_n") or 0)) for s in primary
        )

        pattern = re.compile(
            r"round\s+\d+:\s+\+(\d+)\s+backtest samples,\s+\+(\d+)\s+paper samples"
        )
        observed: list[tuple[int, int]] = []
        # list_jobs is newest-first; reverse to chronological order before
        # keeping the last observations below.
        for job in reversed(self.list_jobs(limit=100)):
            if job.get("kind") not in {"simulator", "evidence"}:
                continue
            if job.get("status") != "succeeded":
                continue
            for match in pattern.finditer(self.tail(job["job_id"], 500)):
                observed.append((int(match.group(1)), int(match.group(2))))
        # Cap the history so ancient/high-yield runs do not dominate a pace
        # that has slowed because most windows now deduplicate.
        observed = observed[-30:]
        bt_rate = sum(x for x, _ in observed) / len(observed) if observed else None
        pp_rate = sum(x for _, x in observed) / len(observed) if observed else None

        if bt_gap == 0 and pp_gap == 0:
            projected = 0
            projection_state = "complete"
        elif not observed:
            projected = None
            projection_state = "unknown"
        elif (bt_gap and not bt_rate) or (pp_gap and not pp_rate):
            projected = None
            projection_state = "stalled"
        else:
            projected = max(
                math.ceil(bt_gap / bt_rate) if bt_gap else 0,
                math.ceil(pp_gap / pp_rate) if pp_gap else 0,
            )
            projection_state = "estimated"

        def _sample_complete(setup: dict) -> bool:
            bt_target = int(setup.get("backtest_target") or 0)
            pp_target = int(setup.get("paper_target") or 0)
            return (
                bt_target > 0
                and pp_target > 0
                and int(setup.get("backtest_n") or 0) >= bt_target
                and int(setup.get("paper_n") or 0) >= pp_target
            )

        incomplete = [s for s in primary if not _sample_complete(s)]
        # Report a completed setup's losing/absent net expectancy immediately,
        # even if another primary setup is still gathering samples. Hiding that
        # result behind the family-wide gap would invite more grinding or tuning
        # of a setup for which the honest measured result is already “no edge”.
        no_edge = [
            s
            for s in primary
            if _sample_complete(s)
            and (s.get("expectancy_net") is None or float(s.get("expectancy_net")) <= 0)
        ]
        proven = [s for s in primary if s.get("proven")]
        no_edge_names = [str(s.get("plan_type")) for s in no_edge]
        if not primary:
            result = "unmeasured"
            headline = "No primary setup has been measured yet."
        elif no_edge:
            names = ", ".join(no_edge_names)
            if incomplete:
                result = "mixed"
                headline = (
                    f"No positive net edge measured for {names}; other primary "
                    "setups are still incomplete. Do not tune parameters just "
                    "to turn this green."
                )
            else:
                result = "no_edge"
                headline = (
                    f"No positive net edge measured for {names}. "
                    "Do not tune parameters just to turn this green."
                )
        elif incomplete:
            result = "incomplete"
            headline = "Evidence is incomplete — keep measuring; do not infer an edge yet."
        elif len(proven) == len(primary):
            result = "edge_measured"
            headline = "Positive net edge measured at the sample bar; graduation rules still apply."
        else:
            result = "mixed"
            headline = "The evidence is mixed; no blanket edge claim is justified."

        return {
            "result": result,
            "headline": headline,
            "no_edge_setups": no_edge_names,
            "primary_setups": len(primary),
            "backtest_gap": bt_gap,
            "paper_gap": pp_gap,
            "projection_state": projection_state,
            "projected_rounds": projected,
            "observed_rounds": len(observed),
            "observed_rate": {
                "backtest_per_round": round(bt_rate, 2) if bt_rate is not None else None,
                "paper_per_round": round(pp_rate, 2) if pp_rate is not None else None,
            },
            "caveat": (
                "Rough estimate from recent aggregate additions; unique-window "
                "deduplication can slow later rounds. It is not a promise."
            ),
        }

    # ── cancellation ─────────────────────────────────────────────────────
    def request_cancel(self, job_id: str, user: dict | None = None) -> dict:
        """Ask the worker to stop a queued/running job. Returns the new state."""
        with self._db() as db:
            row = db.conn.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise JobError(f"no such job: {job_id}")
            if row["status"] in TERMINAL:
                raise JobError(f"job is already {row['status']} and cannot be cancelled")
            if row["status"] == "queued":
                db.conn.execute(
                    "UPDATE jobs SET status='cancelled', cancel_requested=1, "
                    "finished_ts=? WHERE job_id=?",
                    (int(time.time() * 1000), job_id),
                )
            else:
                db.conn.execute("UPDATE jobs SET cancel_requested=1 WHERE job_id=?", (job_id,))
            db.conn.commit()
        self._wake.set()
        return self.get(job_id) or {}

    # ── worker lifecycle ─────────────────────────────────────────────────
    def start(self) -> None:
        """Start the single worker thread once (idempotent).

        Orphan adoption (a server restart) happens once, inside the worker
        thread's first loop — *not* here, because ``submit`` calls ``start``
        on every submission and re-running adoption would mark a job the
        worker just picked up as ``interrupted``.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._worker_loop, name="sky-jobs", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Signal the worker to drain and stop (best effort)."""
        self._wake.set()

    def _worker_loop(self) -> None:
        """Adopt orphaned rows once at boot, then run queued jobs on demand.

        The worker **blocks** on ``_wake`` when idle — it never polls. This
        matters for two reasons: (1) ``submit()``/``request_cancel()`` set
        ``_wake``, so a blocked worker wakes exactly when there is work and
        does zero work otherwise; (2) every ``make_app()`` in the test suite
        constructs a ``JobManager``, and a polling worker would otherwise
        re-open the SQLite database (running the full schema DDL) every
        interval for the life of the process — dozens of leaked threads
        hammering deleted ``tmp_path`` files, which is what pushed CI over
        its timeout. A blocked thread is cheap; a polling thread is not.
        """
        self._adopt_interrupted()
        while True:
            job_id = self._next_queued()
            if job_id is None:
                # Block until a submit/cancel signals work. No timeout: a
                # missed ``_wake`` cannot lose a job, because the loop
                # re-checks the queue after every wake and every job.
                self._wake.wait()
                self._wake.clear()
                continue
            self._run_job(job_id)

    def _next_queued(self) -> str | None:
        with self._db() as db:
            row = db.conn.execute(
                "SELECT job_id FROM jobs WHERE status='queued' ORDER BY created_ts ASC LIMIT 1"
            ).fetchone()
            return row["job_id"] if row else None

    def _adopt_interrupted(self) -> None:
        """A server restart leaves ``running`` rows whose subprocess is gone.

        We never silently re-run them (that could double-apply work), nor
        leave them claiming ``running`` forever — mark them ``interrupted`` so
        the user sees the truth and can re-submit consciously.
        """
        with self._db() as db:
            db.conn.execute(
                "UPDATE jobs SET status='interrupted', finished_ts=?, "
                "error='server restarted mid-run; resubmit to continue' "
                "WHERE status='running'",
                (int(time.time() * 1000),),
            )
            db.conn.commit()

    def _set(self, job_id: str, **fields: Any) -> None:
        """Update one job's mutable columns (no log/params)."""
        allowed = {
            "status",
            "started_ts",
            "finished_ts",
            "step_index",
            "step_total",
            "phase",
            "exit_code",
            "error",
            "cancel_requested",
            "log_path",
        }
        cols = {k: v for k, v in fields.items() if k in allowed}
        if not cols:
            return
        sets = ", ".join(f"{k}=?" for k in cols)
        with self._db() as db:
            db.conn.execute(f"UPDATE jobs SET {sets} WHERE job_id=?", (*cols.values(), job_id))
            db.conn.commit()

    # ── execution ────────────────────────────────────────────────────────
    def _steps_for(self, kind: str, params: dict) -> list[tuple[str, dict]]:
        """Expand a job into its ordered (kind, params) steps.

        Composite mappings are declarative and closed: only names declared in
        the composite specification can reach a child allow-listed job.
        """
        if kind in COMPOSITE_JOBS:
            expanded = []
            for step in COMPOSITE_JOBS[kind]["steps"]:
                child = dict(step.get("params") or {})
                for name in step.get("params_from") or []:
                    child[name] = params.get(name)
                for source, target in (step.get("params_map") or {}).items():
                    child[target] = params.get(source)
                # Validate the concrete child now as a second fail-closed
                # boundary before it reaches the runner.
                build_argv(step["kind"], child)
                expanded.append((step["kind"], child))
            return expanded
        return [(kind, params)]

    def _run_job(self, job_id: str) -> None:
        """Execute one job's steps sequentially, streaming output to the log."""
        with self._db() as db:
            row = db.conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                return
            kind, params_json = row["kind"], row["params_json"]
            try:
                params = json.loads(params_json or "{}")
            except Exception:
                params = {}
            # Re-check cancel before starting (a cancel may have landed while
            # the job sat in the queue).
            if row["cancel_requested"]:
                db.conn.execute(
                    "UPDATE jobs SET status='cancelled', finished_ts=? WHERE job_id=?",
                    (int(time.time() * 1000), job_id),
                )
                db.conn.commit()
                return
            db.conn.execute(
                "UPDATE jobs SET status='running', started_ts=?, phase=? WHERE job_id=?",
                (int(time.time() * 1000), "starting", job_id),
            )
            db.conn.commit()

        steps = self._steps_for(kind, params)
        total = len(steps)
        log_path = self._log_file(job_id)
        # Fresh log per run (the file is the job's output stream).
        log_path.write_text("", encoding="utf-8")

        def _append(line: str) -> None:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

        def _should_cancel() -> bool:
            with self._db() as db:
                r = db.conn.execute(
                    "SELECT cancel_requested FROM jobs WHERE job_id=?", (job_id,)
                ).fetchone()
                return bool(r and r["cancel_requested"])

        for i, (step_kind, step_params) in enumerate(steps):
            if _should_cancel():
                self._set(
                    job_id,
                    status="cancelled",
                    finished_ts=int(time.time() * 1000),
                    phase="cancelled",
                )
                return
            argv = build_argv(step_kind, step_params)
            step_label = (JOB_KINDS.get(step_kind) or {}).get("title", step_kind)
            phase = f"step {i + 1}/{total}: {step_label}" if total > 1 else step_label
            self._set(job_id, step_index=i, step_total=total, phase=phase)
            _append(f"── {phase} — python main.py {' '.join(argv)}")

            code = self._runner(argv, on_line=_append, should_cancel=_should_cancel)
            if _should_cancel() or code == -15:
                self._set(
                    job_id,
                    status="cancelled",
                    exit_code=code,
                    finished_ts=int(time.time() * 1000),
                    phase="cancelled",
                )
                return
            if code != 0:
                self._set(
                    job_id,
                    status="failed",
                    exit_code=code,
                    error=f"step {i + 1} '{step_kind}' exited {code}",
                    finished_ts=int(time.time() * 1000),
                    phase=f"failed at {step_label}",
                )
                return

        self._set(
            job_id,
            status="succeeded",
            exit_code=0,
            step_index=total,
            finished_ts=int(time.time() * 1000),
            phase="done",
        )

    def _default_runner(
        self,
        argv: list[str],
        *,
        on_line: Callable[[str], None],
        should_cancel: Callable[[], bool],
    ) -> int:
        """Run ``python main.py <argv>`` and stream each output line to the log.

        Uses Popen with an unbuffered text pipe so progress lines arrive as
        they are written, not at the end. On cancel, terminate then kill.
        """
        env = dict(os.environ)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["SKY_NO_AUTO_INSTALL"] = "1"
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "main.py"), *argv],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            on_line(line)
            if should_cancel():
                self._terminate(proc)
                return -15
        proc.wait()
        return proc.returncode or 0

    @staticmethod
    def _terminate(proc: subprocess.Popen) -> None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # ── SSE ──────────────────────────────────────────────────────────────
    def events(self, job_id: str, interval: float = 1.0, last_event_id: str | None = None):
        """Yield ``text/event-stream`` frames of a job's persisted state.

        Every frame is a full snapshot, so a client that reconnects (with or
        without ``Last-Event-ID``) resumes from the latest persisted state —
        there is no in-memory sequence to lose. The generator ends after the
        terminal frame so the connection closes cleanly.
        """
        if self.get(job_id) is None:
            yield f"event: error\ndata: {json.dumps({'message': 'no such job', 'job_id': job_id})}\n\n"
            return
        seen_terminal = False
        while True:
            state = self.get(job_id)
            if state is None:
                yield f"event: error\ndata: {json.dumps({'message': 'no such job', 'job_id': job_id})}\n\n"
                return
            seq = f"{job_id}:{state['status']}:{state['step_index']}:{state['finished_ts'] or ''}"
            frame = json.dumps(state, default=str)
            yield f"id: {seq}\nevent: job\ndata: {frame}\n\n"
            if state["status"] in TERMINAL:
                seen_terminal = True
            if seen_terminal:
                return
            time.sleep(interval)
