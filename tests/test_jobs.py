"""P18.3 — persisted background job manager + streaming tests.

The roadmap's "done when": *closing a browser does not kill a job, duplicate
clicks do not start duplicate runs, and progress survives reconnect/restart.*

So these tests pin, in order:

1. **Persistence + worker** — a submitted job runs in the server process
   (not inside a request), writes its log to disk, and lands in a terminal
   state with status/exit_code.
2. **Allow-list** — only declared job kinds and validated arguments can run;
   an unknown kind or a bad parameter is refused *before* anything is queued.
3. **Deduplication** — submitting an identical job while one is live returns
   the existing run, never a second one.
4. **Cancel** — a queued job can be cancelled outright; a running one gets a
   cancel request; a finished one cannot be cancelled.
5. **Restart safety** — a manager that starts over a ``running`` row marks it
   ``interrupted`` rather than silently re-running or lying.
6. **The v1 contract** — ``/api/v1/jobs`` uses the one envelope and typed
   codes, the operator/viewer role split holds, and the SSE endpoint streams
   frames and closes on the terminal state.
"""

from __future__ import annotations

import time

import pytest

from web import api_v1 as apiv1
from web import jobs as jobsmod


# ── fakes ─────────────────────────────────────────────────────────────────
def fake_runner(argv, *, on_line, should_cancel):
    """A deterministic in-process stand-in for the subprocess runner.

    Emits three lines (so the log has content), honours cancel between
    "lines", and returns an exit code the test can observe.
    """
    for _i, text in enumerate(["starting fake work", "doing the thing", "done"]):
        if should_cancel():
            return -15
        on_line(text)
        time.sleep(0.005)
    return 0


def _manager(tmp_path, runner=fake_runner):
    return jobsmod.JobManager(
        db_path=str(tmp_path / "jobs.db"), log_dir=str(tmp_path / "logs"), runner=runner
    )


def _wait(job_id, mgr, statuses, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = mgr.get(job_id)
        if state and state["status"] in statuses:
            return state
        time.sleep(0.02)
    return mgr.get(job_id)


# ══════════════════════════════════════════════════════════════════════════
# 1. persistence + worker
# ══════════════════════════════════════════════════════════════════════════
def test_submit_runs_to_success(tmp_path):
    mgr = _manager(tmp_path)
    res = mgr.submit("backfill", {"symbol": "BTCUSDT", "tf": "1h"})
    assert res["created"] is True
    state = _wait(res["job_id"], mgr, {"succeeded", "failed"})
    assert state["status"] == "succeeded"
    assert state["exit_code"] == 0
    assert "doing the thing" in state["log_tail"]
    assert state["finished_ts"] is not None


def test_failed_step_surfaces_exit_code_and_error(tmp_path):
    def failing(argv, *, on_line, should_cancel):
        on_line("boom")
        return 3

    mgr = _manager(tmp_path, runner=failing)
    res = mgr.submit("backtest", {"symbol": "ETHUSDT"})
    state = _wait(res["job_id"], mgr, {"failed"})
    assert state["status"] == "failed"
    assert state["exit_code"] == 3
    assert "boom" in state["log_tail"]
    assert "backtest" in (state["error"] or "")


def test_job_runs_outside_the_calling_thread(tmp_path):
    """The worker, not the submitter, executes the job — closing the browser
    (the request thread) cannot kill it."""
    started = {"n": 0}

    def counting(argv, *, on_line, should_cancel):
        started["n"] += 1
        on_line("x")
        return 0

    mgr = _manager(tmp_path, runner=counting)
    res = mgr.submit("simulator", {"rounds": 1})
    # The runner should not have executed synchronously inside submit() —
    # submit only enqueues; the worker thread picks it up.
    assert started["n"] == 0
    _wait(res["job_id"], mgr, {"succeeded"})
    assert started["n"] == 1


def test_evidence_guidance_projects_from_observed_rounds_and_reports_no_edge(tmp_path):
    def measured(argv, *, on_line, should_cancel):
        on_line("round 1: +20 backtest samples, +4 paper samples (run sim_test)")
        return 0

    mgr = _manager(tmp_path, runner=measured)
    res = mgr.submit("simulator", {"rounds": 1})
    _wait(res["job_id"], mgr, {"succeeded"})

    incomplete = mgr.evidence_guidance(
        [
            {
                "plan_type": "Sweep Reversal",
                "primary": True,
                "backtest_n": 60,
                "backtest_target": 100,
                "paper_n": 12,
                "paper_target": 20,
                "expectancy_net": -0.1,
                "proven": False,
            }
        ]
    )
    assert incomplete["result"] == "incomplete"
    assert incomplete["projected_rounds"] == 2
    assert incomplete["observed_rounds"] == 1

    finished = mgr.evidence_guidance(
        [
            {
                "plan_type": "Sweep Reversal",
                "primary": True,
                "backtest_n": 100,
                "backtest_target": 100,
                "paper_n": 20,
                "paper_target": 20,
                "expectancy_net": -0.1,
                "proven": False,
            }
        ]
    )
    assert finished["result"] == "no_edge"
    assert finished["projected_rounds"] == 0
    assert "Do not tune" in finished["headline"]


def test_evidence_guidance_reports_completed_no_edge_amid_other_gaps(tmp_path):
    mgr = _manager(tmp_path)
    guidance = mgr.evidence_guidance(
        [
            {
                "plan_type": "Sweep Reversal",
                "primary": True,
                "backtest_n": 100,
                "backtest_target": 100,
                "paper_n": 20,
                "paper_target": 20,
                "expectancy_net": -0.2,
                "proven": False,
            },
            {
                "plan_type": "Trend Continuation",
                "primary": True,
                "backtest_n": 40,
                "backtest_target": 100,
                "paper_n": 5,
                "paper_target": 20,
                "expectancy_net": 0.1,
                "proven": False,
            },
        ]
    )
    assert guidance["result"] == "mixed"
    assert guidance["no_edge_setups"] == ["Sweep Reversal"]
    assert "No positive net edge measured for Sweep Reversal" in guidance["headline"]
    assert "Do not tune" in guidance["headline"]
    assert guidance["backtest_gap"] == 60 and guidance["paper_gap"] == 15


def test_evidence_guidance_is_unknown_then_stalled_without_inventing_a_rate(tmp_path):
    def zero_yield(argv, *, on_line, should_cancel):
        on_line("round 1: +0 backtest samples, +0 paper samples (run sim_zero)")
        return 0

    mgr = _manager(tmp_path, runner=zero_yield)
    gap = [
        {
            "plan_type": "Sweep Reversal",
            "primary": True,
            "backtest_n": 60,
            "backtest_target": 100,
            "paper_n": 12,
            "paper_target": 20,
            "expectancy_net": None,
            "proven": False,
        }
    ]

    unknown = mgr.evidence_guidance(gap)
    assert unknown["projection_state"] == "unknown"
    assert unknown["projected_rounds"] is None
    assert unknown["observed_rate"] == {
        "backtest_per_round": None,
        "paper_per_round": None,
    }

    res = mgr.submit("simulator", {"rounds": 1})
    _wait(res["job_id"], mgr, {"succeeded"})
    stalled = mgr.evidence_guidance(gap)
    assert stalled["projection_state"] == "stalled"
    assert stalled["projected_rounds"] is None
    assert stalled["observed_rate"] == {
        "backtest_per_round": 0.0,
        "paper_per_round": 0.0,
    }


# ══════════════════════════════════════════════════════════════════════════
# 2. allow-list + validation
# ══════════════════════════════════════════════════════════════════════════
def test_unknown_kind_is_refused(tmp_path):
    mgr = _manager(tmp_path)
    with pytest.raises(jobsmod.JobError):
        mgr.submit("rm -rf", {})


def test_bad_choice_param_is_refused(tmp_path):
    mgr = _manager(tmp_path)
    with pytest.raises(jobsmod.JobError):
        mgr.submit("backfill", {"tf": "3h"})  # not an allowed timeframe


def test_bad_int_param_is_refused(tmp_path):
    mgr = _manager(tmp_path)
    with pytest.raises(jobsmod.JobError):
        mgr.submit("simulator", {"rounds": "not-a-number"})


def test_newline_in_param_is_refused(tmp_path):
    mgr = _manager(tmp_path)
    with pytest.raises(jobsmod.JobError):
        mgr.submit("backfill", {"symbol": "BTC\nUSDT"})


def test_evidence_composite_validates_and_maps_one_series(tmp_path):
    mgr = _manager(tmp_path)
    params = jobsmod.validate_composite(
        "evidence",
        {
            "symbol": "ETHUSDT",
            "tf": "1h",
            "market": "spot",
            "since": "90d",
            "bars": 900,
            "rounds": 7,
        },
    )
    steps = mgr._steps_for("evidence", params)
    assert steps == [
        (
            "backfill",
            {"symbol": "ETHUSDT", "tf": "1h", "market": "spot", "since": "90d"},
        ),
        ("backtest", {"symbol": "ETHUSDT", "tf": "1h", "bars": 900}),
        ("simulator", {"symbols": "ETHUSDT", "tf": "1h", "rounds": 7}),
        ("scorecard", {"source": "db"}),
    ]
    assert "ETHUSDT" in jobsmod.build_argv(*steps[0])
    assert "ETHUSDT" in jobsmod.build_argv(*steps[2])


def test_evidence_composite_refuses_unknown_or_unbounded_inputs(tmp_path):
    mgr = _manager(tmp_path)
    with pytest.raises(jobsmod.JobError):
        mgr.submit("evidence", {"shell": "anything"})
    with pytest.raises(jobsmod.JobError):
        mgr.submit("evidence", {"rounds": 0})
    with pytest.raises(jobsmod.JobError):
        mgr.submit("evidence", {"tf": "3h"})
    assert mgr.list_jobs() == []  # every refusal happened before persistence


# ══════════════════════════════════════════════════════════════════════════
# 3. deduplication
# ══════════════════════════════════════════════════════════════════════════
def test_duplicate_submission_returns_existing_job(tmp_path):
    """A duplicate click must not start a duplicate run."""
    gate = {"release": False}

    def slow(argv, *, on_line, should_cancel):
        while not gate["release"]:
            time.sleep(0.01)
            if should_cancel():
                return -15
        return 0

    mgr = _manager(tmp_path, runner=slow)
    first = mgr.submit("backfill", {"symbol": "BTCUSDT", "tf": "1m"})
    second = mgr.submit("backfill", {"symbol": "BTCUSDT", "tf": "1m"})
    gate["release"] = True
    assert first["created"] is True
    assert second["created"] is False
    assert second["job_id"] == first["job_id"]
    # And there is exactly one job row, not two.
    assert len(mgr.list_jobs()) == 1


def test_different_params_are_not_a_duplicate(tmp_path):
    mgr = _manager(tmp_path)
    a = mgr.submit("backfill", {"symbol": "BTCUSDT", "tf": "1m"})
    b = mgr.submit("backfill", {"symbol": "BTCUSDT", "tf": "5m"})
    assert a["job_id"] != b["job_id"]
    assert a["created"] and b["created"]


# ══════════════════════════════════════════════════════════════════════════
# 4. cancel
# ══════════════════════════════════════════════════════════════════════════
def test_cancel_queued_job(tmp_path):
    """A job still in the queue is cancelled outright, before it runs."""
    gate = {"release": False}

    def blocking(argv, *, on_line, should_cancel):
        on_line("started")
        while not gate["release"]:
            time.sleep(0.01)
            if should_cancel():
                return -15
        return 0

    mgr = _manager(tmp_path, runner=blocking)
    # Occupy the single worker with a blocking job so the second stays queued.
    a = mgr.submit("backfill", {"symbol": "BTCUSDT"})
    _wait(a["job_id"], mgr, {"running"})
    b = mgr.submit("backtest", {"symbol": "ETHUSDT"})
    assert mgr.get(b["job_id"])["status"] == "queued"
    state = mgr.request_cancel(b["job_id"])
    assert state["status"] == "cancelled"
    gate["release"] = True
    # The cancelled job is never picked up once the worker drains.
    _wait(a["job_id"], mgr, {"succeeded"})
    assert mgr.get(b["job_id"])["status"] == "cancelled"


def test_cancel_running_job(tmp_path):
    started = {"n": 0}

    def slow(argv, *, on_line, should_cancel):
        started["n"] += 1
        on_line("started")
        while not should_cancel():
            time.sleep(0.01)
        return -15

    mgr = _manager(tmp_path, runner=slow)
    res = mgr.submit("simulator", {"rounds": 3})
    # Wait until the worker actually starts the run, then cancel it.
    _wait(res["job_id"], mgr, {"running"})
    state = mgr.request_cancel(res["job_id"])
    state = _wait(res["job_id"], mgr, {"cancelled"})
    assert state["status"] == "cancelled"


def test_cancel_finished_job_is_refused(tmp_path):
    mgr = _manager(tmp_path)
    res = mgr.submit("scorecard", {})
    _wait(res["job_id"], mgr, {"succeeded"})
    with pytest.raises(jobsmod.JobError):
        mgr.request_cancel(res["job_id"])


# ══════════════════════════════════════════════════════════════════════════
# 5. restart safety
# ══════════════════════════════════════════════════════════════════════════
def test_orphaned_running_row_is_marked_interrupted(tmp_path):
    """A server restart must not silently re-run a half-done job, nor leave it
    claiming ``running`` forever."""
    db_path = str(tmp_path / "jobs.db")
    log_dir = str(tmp_path / "logs")
    mgr1 = _manager(tmp_path)
    res = mgr1.submit("backfill", {"symbol": "BTCUSDT"})
    _wait(res["job_id"], mgr1, {"succeeded"})
    # Simulate a crash: the row is left 'running' with a finished process.
    from data.database import SignalDB

    with SignalDB(db_path) as db:
        db.conn.execute("UPDATE jobs SET status='running' WHERE job_id=?", (res["job_id"],))
        db.conn.commit()
    # A fresh manager adopts the orphan and reports the truth.
    mgr2 = jobsmod.JobManager(db_path=db_path, log_dir=log_dir, runner=fake_runner)
    mgr2.start()  # boot-time adoption of orphaned rows
    state = _wait(res["job_id"], mgr2, {"interrupted"})
    assert state["status"] == "interrupted"
    assert "restart" in (state["error"] or "")


def test_worker_blocks_when_idle_does_not_poll(monkeypatch, tmp_path):
    """Regression: the idle worker must *block*, not poll the database.

    The original worker re-opened ``SignalDB`` (running the full schema DDL)
    on a fixed interval while idle. Because every ``make_app()`` constructs a
    ``JobManager``, the test suite leaked dozens of those polling threads,
    each hammering its own (soon-deleted) ``tmp_path`` database — enough to
    push CI's 10-minute budget over. A blocked worker touches the DB exactly
    zero times once the queue is drained.
    """
    opens = {"n": 0}
    orig_db = jobsmod.JobManager._db

    def counting_db(self):
        opens["n"] += 1
        return orig_db(self)

    monkeypatch.setattr(jobsmod.JobManager, "_db", counting_db)
    mgr = _manager(tmp_path)
    res = mgr.submit("scorecard", {})
    _wait(res["job_id"], mgr, {"succeeded"})
    # Let the worker finish its *final* queue re-check (one open) and settle
    # into blocking. Then take a baseline and assert nothing else opens: a
    # polling worker — if one were reintroduced — would keep opening the DB.
    time.sleep(0.5)
    baseline = opens["n"]
    time.sleep(0.8)
    assert opens["n"] == baseline, (
        f"idle worker polled the database: {opens['n']} opens after {baseline}"
    )


# ══════════════════════════════════════════════════════════════════════════
# 6. the v1 contract
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def open_app(monkeypatch, tmp_path):
    """Auth-disabled app whose job manager uses a fast fake runner."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "web.db"))
    import config as _c

    monkeypatch.setattr(_c, "DB_PATH", str(tmp_path / "web.db"))
    monkeypatch.setattr(_c, "SKY_AUTH_MODE", "disabled")
    mgr = jobsmod.JobManager(
        db_path=str(tmp_path / "jm.db"),
        log_dir=str(tmp_path / "logs"),
        runner=fake_runner,
    )
    from web.app import make_app

    application = make_app(job_manager=mgr)
    application.testing = True
    return application, mgr


@pytest.fixture
def open_client(open_app):
    return open_app[0].test_client()


@pytest.fixture
def open_mgr(open_app):
    return open_app[1]


def _wait_v1(job_id, mgr, statuses, timeout=5.0):
    return _wait(job_id, mgr, statuses, timeout)


def test_v1_jobs_list_is_enveloped(open_client):
    r = open_client.get("/api/v1/jobs")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["error"] is None
    assert "jobs" in body["data"]
    assert "kinds" in body["data"]


def test_v1_submit_and_stream(open_client, open_mgr):
    r = open_client.post("/api/v1/jobs", json={"kind": "backfill", "params": {"symbol": "BTCUSDT"}})
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["data"]["created"] is True
    job_id = body["data"]["job"]["job_id"]

    state = _wait_v1(job_id, open_mgr, {"succeeded"})
    assert state["status"] == "succeeded"

    r = open_client.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200
    assert r.get_json()["data"]["job"]["status"] == "succeeded"


def test_v1_unknown_kind_is_validation_failed(open_client):
    r = open_client.post("/api/v1/jobs", json={"kind": "rm -rf", "params": {}})
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"]["code"] == apiv1.ErrorCode.VALIDATION_FAILED


def test_v1_unknown_job_is_typed_not_found(open_client):
    r = open_client.get("/api/v1/jobs/nope")
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.JOB_NOT_FOUND


def test_v1_cancel_unknown_job_is_typed(open_client):
    r = open_client.post("/api/v1/jobs/nope/cancel")
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.JOB_NOT_CANCELLABLE


def test_v1_events_streams_and_closes(open_client, open_mgr):
    r = open_client.post("/api/v1/jobs", json={"kind": "scorecard", "params": {}})
    job_id = r.get_json()["data"]["job"]["job_id"]
    _wait_v1(job_id, open_mgr, {"succeeded"})
    # A finished job's stream emits one terminal frame then closes.
    resp = open_client.get(f"/api/v1/jobs/{job_id}/events", buffered=False)
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    text = resp.get_data(as_text=True)
    assert "event: job" in text
    assert '"status": "succeeded"' in text


def test_v1_duplicate_submission_is_reported(open_client, open_mgr):
    gate = {"release": False}

    def slow(argv, *, on_line, should_cancel):
        while not gate["release"]:
            time.sleep(0.01)
            if should_cancel():
                return -15
        return 0

    open_mgr._runner = slow
    r1 = open_client.post(
        "/api/v1/jobs", json={"kind": "backfill", "params": {"symbol": "ETHUSDT"}}
    )
    r2 = open_client.post(
        "/api/v1/jobs", json={"kind": "backfill", "params": {"symbol": "ETHUSDT"}}
    )
    gate["release"] = True
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r2.get_json()["data"]["duplicate"] is True
    assert r2.get_json()["data"]["job"]["job_id"] == r1.get_json()["data"]["job"]["job_id"]


def test_v1_role_split(monkeypatch, tmp_path):
    """Submitting a job is an operator action; listing/viewing is viewer."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "role.db"))
    import config as _c

    monkeypatch.setattr(_c, "DB_PATH", str(tmp_path / "role.db"))
    monkeypatch.setattr(_c, "SKY_AUTH_MODE", "auto")
    monkeypatch.setattr(_c, "SKY_ALLOW_FORCE_APPROVE", False)
    monkeypatch.setattr(_c, "SKY_TRUSTED_PROXY_IPS", [])
    mgr = jobsmod.JobManager(
        db_path=str(tmp_path / "jm2.db"),
        log_dir=str(tmp_path / "logs2"),
        runner=fake_runner,
    )
    from web.app import make_app

    application = make_app(job_manager=mgr)
    application.testing = True
    client = application.test_client()

    # First-run owner creation (the P18.1 flow).
    r = client.post(
        "/api/auth/setup",
        json={"username": "owner", "password": "correct horse battery staple"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    csrf = r.get_json()["csrf"]

    # Owner (operator) can submit.
    r = client.post(
        "/api/v1/jobs",
        json={"kind": "scorecard", "params": {}},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    job_id = r.get_json()["data"]["job"]["job_id"]

    # A viewer-scoped device token can list and read, but not submit.
    tok = client.post(
        "/api/v1/devices",
        json={"name": "v", "scope": "viewer"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()["data"]["token"]
    h = {"Authorization": f"Bearer {tok}"}
    anon = application.test_client()  # no owner session cookie — token only
    assert anon.get("/api/v1/jobs", headers=h).status_code == 200
    assert anon.get(f"/api/v1/jobs/{job_id}", headers=h).status_code == 200
    r = anon.post("/api/v1/jobs", json={"kind": "backfill", "params": {}}, headers=h)
    assert r.status_code == 403
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.FORBIDDEN


def test_v1_cancel_requires_operator(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "role2.db"))
    import config as _c

    monkeypatch.setattr(_c, "DB_PATH", str(tmp_path / "role2.db"))
    monkeypatch.setattr(_c, "SKY_AUTH_MODE", "auto")
    monkeypatch.setattr(_c, "SKY_ALLOW_FORCE_APPROVE", False)
    monkeypatch.setattr(_c, "SKY_TRUSTED_PROXY_IPS", [])
    mgr = jobsmod.JobManager(
        db_path=str(tmp_path / "jm3.db"),
        log_dir=str(tmp_path / "logs3"),
        runner=fake_runner,
    )
    from web.app import make_app

    application = make_app(job_manager=mgr)
    application.testing = True
    client = application.test_client()
    r = client.post(
        "/api/auth/setup",
        json={"username": "owner", "password": "correct horse battery staple"},
    )
    csrf = r.get_json()["csrf"]
    r = client.post(
        "/api/v1/jobs",
        json={"kind": "scorecard", "params": {}},
        headers={"X-CSRF-Token": csrf},
    )
    job_id = r.get_json()["data"]["job"]["job_id"]
    tok = client.post(
        "/api/v1/devices",
        json={"name": "v", "scope": "viewer"},
        headers={"X-CSRF-Token": csrf},
    ).get_json()["data"]["token"]
    h = {"Authorization": f"Bearer {tok}"}
    anon = application.test_client()
    r = anon.post(f"/api/v1/jobs/{job_id}/cancel", headers=h)
    assert r.status_code == 403
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.FORBIDDEN


def test_job_route_catalog_includes_jobs(open_client):
    routes = open_client.get("/api/v1/routes").get_json()["data"]["routes"]
    paths = [r["path"] for r in routes]
    assert "/api/v1/jobs" in paths
    assert "/api/v1/jobs/<job_id>" in paths
    assert "/api/v1/jobs/<job_id>/events" in paths
