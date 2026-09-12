"""
core/collective/provenance.py
=============================
Authoritative provenance enforcement for SDCC collective events.
Section 30: "A number without provenance is not trustworthy evidence."
"""

from __future__ import annotations

import logging
from typing import Any

from core.collective.event import CanonicalEvent

logger = logging.getLogger("sky.collective.provenance")


def validate_event_provenance(event: CanonicalEvent) -> tuple[bool, str | None]:
    """
    Validates provenance integrity on an incoming canonical event.
    Returns (True, None) if valid, or (False, reason) if incomplete or fabricated.
    """
    prov = event.provenance
    if not prov or not isinstance(prov, dict):
        return False, "Missing provenance dictionary block"

    # Mandatory baseline fields
    if not prov.get("source_type"):
        return False, "Missing mandatory provenance field 'source_type'"

    if not prov.get("node_id"):
        return False, "Missing mandatory provenance field 'node_id'"

    if prov.get("node_id") != event.node_id:
        return (
            False,
            f"Provenance node_id '{prov.get('node_id')}' does not match event envelope node_id '{event.node_id}'",
        )

    # Domain specific provenance checks
    etype = event.event_type
    if etype.startswith("PAPER_"):
        # Paper trades require symbol and valid execution model or strategy context
        if event.payload and "symbol" not in event.payload:
            return False, "Paper trading event payload missing required 'symbol'"

    elif etype in ["EXPERIMENT_COMPLETED", "STRATEGY_EVALUATED"]:
        # Experiments require code version or dataset hash
        if not (prov.get("code_version") or prov.get("dataset_id") or prov.get("strategy_id")):
            return (
                False,
                f"Empirical evaluation event {event.event_id} missing code_version, dataset_id, or strategy_id provenance",
            )

    return True, None
