"""engine/calibration_hook.py

Applies the self-improvement profile to one plan's confidence.

Profiles are stored per setup — and since the professional-mode learning loop
is regime-tagged (decision B3), a profile key may be either ``plan_type`` or
``plan_type::regime``.  The composite key wins when present, so the engine can
know *"this setup works in TRENDING_BULL but not in RANGING"*.

**P12.11 — source provenance.** A key may also carry ``@exchange:market[:side]``
identifying the price series it was learned from. This hook is the *live*
path: it resolves keys for the **canonical** series only (Binance spot,
two-sided, written as the empty source key), so a Dukascopy XAUUSD bid-only
research profile — filed under ``…@dukascopy:spot:bid`` — is never matched
and can never move the confidence of a live signal. Profiles written before
P12.11 have no suffix, so they resolve exactly as they always did.
"""
from __future__ import annotations

from data.provenance import KEY_SEP, LIVE_SOURCE_KEY
from data.provenance import parse_source_key as _parse_source_key
from data.provenance import source_key as _source_key


def _composite(plan_type: str, regime: str, source: str = LIVE_SOURCE_KEY) -> str:
    base = f"{plan_type}::{regime}" if regime else plan_type
    return f"{base}{KEY_SEP}{source}" if source else base


def apply_calibration(conf: int, plan_type: str, calibration: dict,
                      regime: str = "",
                      source_key: str = LIVE_SOURCE_KEY) -> tuple[int, bool]:
    """Return (adjusted_confidence, filtered_out).

    Lookup narrows from ``plan_type::regime`` to ``plan_type`` **within one
    source series**; it never falls back across sources.
    """
    if not calibration:
        return conf, False
    src = _source_key(*_parse_source_key(source_key))
    entry = calibration.get(_composite(plan_type, regime, src))
    if entry is None:
        entry = calibration.get(_composite(plan_type, "", src))
    if not entry:
        return conf, False
    if entry.get("filtered"):
        return conf, True
    mult = entry.get("multiplier", 1.0)
    return max(5, min(100, int(round(conf * mult)))), False
