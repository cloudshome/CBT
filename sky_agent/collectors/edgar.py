"""sky_agent.collectors.edgar — SEC EDGAR ingestion (consumer, not filer).

Official endpoints: https://data.sec.gov (no API key, fair-access ≤10 req/s).
Uses bulk where possible; live poll for recent filings.

Storage is idempotent on accession PK; backtester must join on acceptance_datetime,
never periodOfReport (look-ahead bias guard).

Refs: discovery doc §5, SEC fair-access docs cited in *03.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Optional
import os

import requests

from sky_agent.config import SEC_USER_AGENT, SEC_MAX_RPS

SEC_BASE = "https://data.sec.gov"
SEC_SUBMISSIONS = SEC_BASE + "/submissions/CIK{cik:010d}.json"
SEC_TICKER_MAP = SEC_BASE + "/submissions/CIK{cik:010d}.json"  # same; ticker→cik via lookup below
TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
XBRL_FACTS_URL = SEC_BASE + "/api/xbrl/companyfacts/CIK{cik:010d}.json"

# Bulk archives (for backfill): https://www.sec.gov/Archives/edgar/daily-index/
# and quarterly full-index ZIPs — not fetched by default in the daemon.

FORMS_OF_INTEREST = ("8-K", "10-Q", "10-K", "20-F", "6-K", "S-1", "S-3")

# Minimal event taxonomy for 8-K (extendable)
EVENT_TAXONOMY = {
    "bankruptcy": {"severity": 5, "direction": "bearish", "match": re.compile(r"bankruptcy|chapter\s*11", re.I)},
    "going_concern": {"severity": 5, "direction": "bearish", "match": re.compile(r"going concern", re.I)},
    "ceo_resignation": {"severity": 3, "direction": "context", "match": re.compile(r"ceo.*resign|resignation.*ceo|chief executive", re.I)},
    "acquisition": {"severity": 3, "direction": "context", "match": re.compile(r"acquisition|merger", re.I)},
    "debt_default": {"severity": 5, "direction": "bearish", "match": re.compile(r"default.*debt|debt.*default", re.I)},
    "major_contract": {"severity": 4, "direction": "bullish", "match": re.compile(r"material.*definitive.*agreement|major.*contract", re.I)},
    "secondary_offering": {"severity": 4, "direction": "bearish", "match": re.compile(r"secondary offering|at-the-market", re.I)},
    "buyback": {"severity": 3, "direction": "bullish", "match": re.compile(r"share.*repurchase|buyback", re.I)},
    "guidance_increase": {"severity": 4, "direction": "bullish", "match": re.compile(r"guidance.*increase|raise.*outlook", re.I)},
    "guidance_reduction": {"severity": 4, "direction": "bearish", "match": re.compile(r"guidance.*reduc|lower.*outlook|cut.*forecast", re.I)},
    "litigation": {"severity": 3, "direction": "bearish", "match": re.compile(r"litigation|lawsuit", re.I)},
    "earnings_release": {"severity": 4, "direction": "context", "match": re.compile(r"earnings.*release|results.*operations", re.I)},
}

_last_req_ts = 0.0


def _throttle() -> None:
    global _last_req_ts
    min_interval = 1.0 / max(SEC_MAX_RPS, 0.5)
    now = time.monotonic()
    wait = _last_req_ts + min_interval - now
    if wait > 0:
        time.sleep(wait)
    _last_req_ts = time.monotonic()


def _headers() -> dict[str, str]:
    return {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip", "Host": "data.sec.gov"}


def fetch_json(url: str, *, timeout: int = 15) -> dict[str, Any]:
    if os.getenv("DEMO_MODE") == "1":
        # Deterministic offline stub
        return {"demo": True, "url": url, "filings": {"recent": {"accessionNumber": [], "form": [], "filingDate": [], "acceptanceDateTime": [], "reportDate": []}}}
    _throttle()
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def ticker_cik_map() -> dict[str, str]:
    """Return {TICKER -> zero-padded CIK}."""
    data = fetch_json(TICKER_CIK_URL)
    out: dict[str, str] = {}
    # Shape: {0:{cik_str, ticker, title}, 1:…}
    for v in data.values() if isinstance(data, dict) else []:
        if isinstance(v, dict) and "ticker" in v and "cik_str" in v:
            out[str(v["ticker"]).upper()] = f"{int(v['cik_str']):010d}"
    return out


def fetch_submissions(cik: str | int) -> dict[str, Any]:
    cik10 = f"{int(str(cik).strip()):010d}"
    return fetch_json(SEC_SUBMISSIONS.format(cik=cik10))


def classify_event_text(text: str) -> tuple[str, int, str]:
    """Return (event_type, severity, direction) for a filing snippet."""
    for etype, spec in EVENT_TAXONOMY.items():
        if spec["match"].search(text or ""):
            return etype, int(spec["severity"]), str(spec["direction"])
    return "other", 2, "context"


def ingest_recent_filings(*, tickers: list[str] | None = None, ciks: list[str] | None = None, limit: int = 20, demo: bool = False) -> list[dict[str, Any]]:
    """Fetch recent filings for a small universe; return normalised rows ready for upsert.

    Idempotent: callers should upsert on accession PK.
    """
    if demo or os.getenv("DEMO_MODE") == "1":
        # Deterministic fake — exercises the full path without network
        return [
            {
                "accession": "0000000000-26-000001",
                "cik": "0000320193",
                "ticker": "AAPL",
                "form": "8-K",
                "filing_date": "2026-08-18",
                "acceptance_datetime": "2026-08-18T14:31:00.000Z",
                "period_of_report": "2026-08-18",
                "url": "https://www.sec.gov/Archives/edgar/data/320193/000000000026000001/0000000000-26-000001-index.html",
                "raw": {"demo": True},
                "event_type": "earnings_release",
                "severity": 4,
                "direction": "context",
            }
        ]

    universe_ciks: list[str] = []
    if ciks:
        universe_ciks = [f"{int(c):010d}" for c in ciks]
    elif tickers:
        m = ticker_cik_map()
        for t in tickers:
            cik = m.get(t.upper())
            if cik:
                universe_ciks.append(cik)
    else:
        # Small default crypto-relevant universe (miners, exchanges, semis)
        universe_ciks = []

    rows: list[dict[str, Any]] = []
    for cik in universe_ciks[:50]:
        try:
            data = fetch_submissions(cik)
            filings = data.get("filings", {}).get("recent", {})
            n = min(limit, len(filings.get("accessionNumber", [])))
            for i in range(n):
                form = filings.get("form", [""])[i]
                if form not in FORMS_OF_INTEREST:
                    continue
                acc = filings.get("accessionNumber", [""])[i]
                fdate = filings.get("filingDate", [""])[i]
                adt = filings.get("acceptanceDateTime", [""])[i]
                report = filings.get("reportDate", [""])[i] if "reportDate" in filings else ""
                # Best-effort event classification from form + description
                etype, sev, direction = classify_event_text(f"{form} {adt}")
                rows.append({
                    "accession": acc,
                    "cik": cik,
                    "ticker": "",
                    "form": form,
                    "filing_date": fdate,
                    "acceptance_datetime": adt,
                    "period_of_report": report,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/{acc}-index.html",
                    "raw": {"cik": cik, "form": form},
                    "event_type": etype,
                    "severity": sev,
                    "direction": direction,
                })
        except Exception:
            continue
    return rows


def upsert_filings(rows: list[dict[str, Any]], *, db=None) -> int:
    """Upsert filing rows into sec_filings + sec_events. Returns count."""
    close = False
    if db is None:
        from data.database import SignalDB
        db = SignalDB()
        close = True
    try:
        from sky_agent.memory import ensure_memory_schema
        ensure_memory_schema(db)
        count = 0
        for r in rows:
            acc = r.get("accession")
            if not acc:
                continue
            db.conn.execute(
                "INSERT OR REPLACE INTO sec_filings(accession,cik,ticker,form,filing_date,acceptance_datetime,period_of_report,url,raw_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (acc, r.get("cik"), r.get("ticker"), r.get("form"), r.get("filing_date"), r.get("acceptance_datetime"), r.get("period_of_report"), r.get("url"), json.dumps(r.get("raw") or {})),
            )
            # Event row (one per filing for MVP)
            db.conn.execute(
                "INSERT INTO sec_events(accession,event_type,severity,direction,score,classification,created_ts) VALUES (?,?,?,?,?,?,?)",
                (acc, r.get("event_type", "other"), int(r.get("severity", 2)), r.get("direction", "context"), int(r.get("severity", 2)) * 20, r.get("form"), int(time.time())),
            )
            count += 1
        db.conn.commit()
        return count
    finally:
        if close:
            db.close()
