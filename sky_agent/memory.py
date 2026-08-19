"""sky_agent.memory — structured memory tables for the intelligence agent."""
from __future__ import annotations

import json
import time
import sqlite3
from pathlib import Path
from typing import Any

# Reuse canonical DB path resolution
from data.database import SignalDB

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_hypotheses(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hypothesis_id TEXT UNIQUE,
  setup TEXT,
  filters_json TEXT,
  status TEXT DEFAULT 'proposed',
  created_ts INTEGER,
  tested_ts INTEGER,
  metrics_json TEXT,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS sec_filings(
  accession TEXT PRIMARY KEY,
  cik TEXT,
  ticker TEXT,
  form TEXT,
  filing_date TEXT,
  acceptance_datetime TEXT,
  period_of_report TEXT,
  url TEXT,
  raw_json TEXT
);
CREATE TABLE IF NOT EXISTS sec_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  accession TEXT,
  event_type TEXT,
  severity INTEGER,
  direction TEXT,
  score INTEGER,
  classification TEXT,
  created_ts INTEGER,
  FOREIGN KEY(accession) REFERENCES sec_filings(accession)
);
CREATE TABLE IF NOT EXISTS sec_xbrl_facts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cik TEXT,
  concept TEXT,
  period TEXT,
  value REAL,
  unit TEXT,
  filing_ts INTEGER
);
CREATE TABLE IF NOT EXISTS intelligence_reports(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_date TEXT,
  kind TEXT,
  asset TEXT,
  timeframe TEXT,
  recommendation TEXT,
  confidence TEXT,
  level TEXT,
  evidence_json TEXT,
  created_ts INTEGER
);
CREATE TABLE IF NOT EXISTS market_regime_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER,
  symbol TEXT,
  timeframe TEXT,
  regime TEXT,
  volatility_state TEXT,
  details_json TEXT
);
"""


def ensure_memory_schema(db: SignalDB | None = None) -> None:
    close = False
    if db is None:
        db = SignalDB()
        close = True
    try:
        db.conn.executescript(MEMORY_SCHEMA)
        db.conn.commit()
    finally:
        if close:
            db.close()


def record_regime(db: SignalDB, *, symbol: str, timeframe: str, regime: str, volatility_state: str, details: dict) -> None:
    ensure_memory_schema(db)
    db.conn.execute(
        "INSERT INTO market_regime_log(ts,symbol,timeframe,regime,volatility_state,details_json) VALUES (?,?,?,?,?,?)",
        (int(time.time()), symbol, timeframe, regime, volatility_state, json.dumps(details)),
    )
    db.conn.commit()


def record_report(db: SignalDB, *, kind: str, asset: str, timeframe: str, recommendation: str, confidence: str, level: str, evidence: dict) -> int:
    ensure_memory_schema(db)
    cur = db.conn.execute(
        "INSERT INTO intelligence_reports(report_date,kind,asset,timeframe,recommendation,confidence,level,evidence_json,created_ts) VALUES (?,?,?,?,?,?,?,?,?)",
        (time.strftime("%Y-%m-%d"), kind, asset, timeframe, recommendation, confidence, level, json.dumps(evidence), int(time.time())),
    )
    db.conn.commit()
    return cur.lastrowid


def upsert_hypothesis(db: SignalDB, *, hypothesis_id: str, setup: str, filters: dict, status: str = "proposed", metrics: dict | None = None, notes: str = "") -> None:
    ensure_memory_schema(db)
    existing = db.conn.execute("SELECT id FROM research_hypotheses WHERE hypothesis_id=?", (hypothesis_id,)).fetchone()
    if existing:
        db.conn.execute(
            "UPDATE research_hypotheses SET setup=?, filters_json=?, status=?, tested_ts=?, metrics_json=?, notes=? WHERE hypothesis_id=?",
            (setup, json.dumps(filters), status, int(time.time()) if status in ("tested", "accepted", "rejected") else None, json.dumps(metrics or {}), notes, hypothesis_id),
        )
    else:
        db.conn.execute(
            "INSERT INTO research_hypotheses(hypothesis_id,setup,filters_json,status,created_ts,tested_ts,metrics_json,notes) VALUES (?,?,?,?,?,?,?,?)",
            (hypothesis_id, setup, json.dumps(filters), status, int(time.time()), None, json.dumps(metrics or {}), notes),
        )
    db.conn.commit()
