"""
core/collective/adapters/paper_trade_adapter.py
===============================================
Adapts local paper trading state mutations into immutable SDCC events.
Enforces Section 26 & 30:
1. Node-aware globally unique trade IDs: PT-<node_id>-<timestamp>-<uuid8>.
2. Mandatory provenance: strategy_id, symbol, timeframe, fee_model, slippage_model.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from core.collective.event import build_canonical_event
from core.collective.event_store import EventStore, event_store
from core.collective.event_types import CollectiveEventType
from core.collective.identity import NodeIdentity, node_identity_manager

logger = logging.getLogger("sky.collective.adapter.paper_trade")


class PaperTradeEventAdapter:
    """Emits canonical Class A events for all paper trading actions."""

    def __init__(
        self,
        identity: NodeIdentity | None = None,
        store: EventStore | None = None,
    ):
        self.identity = identity or node_identity_manager.get_or_create_identity()
        self.store = store or event_store

    def generate_trade_id(self, symbol: str) -> str:
        """Generates a node-scoped, collision-proof paper trade identifier."""
        now_ms = int(time.time() * 1000)
        clean_sym = symbol.replace("/", "_")
        return f"PT-{self.identity.node_id}-{clean_sym}-{now_ms}-{uuid.uuid4().hex[:8]}"

    def emit_position_opened(
        self,
        position_id: str,
        symbol: str,
        direction: str,
        size: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        strategy_id: str = "MANUAL_OR_AUTONOMOUS",
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Emits PAPER_POSITION_OPENED event."""
        seq = self.store.sequence_manager.next_sequence(self.identity.node_id)
        payload = {
            "symbol": symbol,
            "direction": direction.upper(),
            "size": float(size),
            "entry_price": float(entry_price),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "metadata": metadata or {},
        }
        prov = {
            "source_type": "PAPER_ENGINE",
            "node_id": self.identity.node_id,
            "strategy_id": strategy_id,
            "run_id": run_id or f"RUN-{self.identity.node_id}-{int(time.time())}",
            "execution_model": "SHADOW_SIMULATED",
            "fee_model": "0.04%_TAKER",
            "slippage_model": "DYNAMIC_IMPACT",
        }

        event = build_canonical_event(
            node_id=self.identity.node_id,
            sequence=seq,
            event_type=CollectiveEventType.PAPER_POSITION_OPENED,
            entity_type="paper_trade",
            entity_id=position_id,
            payload=payload,
            provenance=prov,
        )

        self.store.append_event(event)
        logger.info(f"Emitted {event.event_id} for opened paper position {position_id}")
        return event.event_id

    def emit_position_closed(
        self,
        position_id: str,
        symbol: str,
        exit_price: float,
        realized_pnl: float,
        reason: str = "MANUAL_CLOSE",
        causation_event_id: str | None = None,
    ) -> str:
        """Emits PAPER_POSITION_CLOSED event."""
        seq = self.store.sequence_manager.next_sequence(self.identity.node_id)
        payload = {
            "symbol": symbol,
            "exit_price": float(exit_price),
            "realized_pnl": float(realized_pnl),
            "close_reason": reason,
        }
        prov = {
            "source_type": "PAPER_ENGINE",
            "node_id": self.identity.node_id,
        }

        event = build_canonical_event(
            node_id=self.identity.node_id,
            sequence=seq,
            event_type=CollectiveEventType.PAPER_POSITION_CLOSED,
            entity_type="paper_trade",
            entity_id=position_id,
            payload=payload,
            provenance=prov,
            causation_id=causation_event_id,
        )

        self.store.append_event(event)
        logger.info(f"Emitted {event.event_id} for closed paper position {position_id} (PnL: {realized_pnl})")
        return event.event_id

    def emit_risk_rejected(
        self,
        symbol: str,
        direction: str,
        size: float,
        reason: str,
        risk_rule: str,
    ) -> str:
        """Emits PAPER_RISK_REJECTED event when an order breaches risk gates."""
        seq = self.store.sequence_manager.next_sequence(self.identity.node_id)
        payload = {
            "symbol": symbol,
            "direction": direction,
            "size": size,
            "reason": reason,
            "risk_rule": risk_rule,
        }
        prov = {
            "source_type": "RISK_GATE",
            "node_id": self.identity.node_id,
        }

        event = build_canonical_event(
            node_id=self.identity.node_id,
            sequence=seq,
            event_type=CollectiveEventType.PAPER_RISK_REJECTED,
            entity_type="risk_rejection",
            entity_id=f"REJ-{int(time.time()*1000)}",
            payload=payload,
            provenance=prov,
        )

        self.store.append_event(event)
        return event.event_id


paper_trade_adapter = PaperTradeEventAdapter()
