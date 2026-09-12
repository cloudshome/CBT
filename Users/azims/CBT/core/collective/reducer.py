"""
core/collective/reducer.py
==========================
Deterministic state reducers for SDCC.

Core Invariant (Section 40 & 64):
  Any permutation of the same valid event set produces an IDENTICAL materialized state:
  State = Reduce(CausalOrder(AllValidEvents))
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from core.collective.event import CanonicalEvent
from core.collective.event_hash import canonical_json_bytes, canonical_json_str
from core.collective.event_types import CollectiveEventType

logger = logging.getLogger("sky.collective.reducer")


def causal_sort_events(events: list[CanonicalEvent]) -> list[CanonicalEvent]:
    """
    Sorts events deterministically:
    1. Causal dependencies first (topological sort on causation_id).
    2. Primary tie-breaker: created_at timestamp string.
    3. Secondary tie-breaker: (node_id, sequence) tuple.
    """
    # Map event_id to event
    by_id: dict[str, CanonicalEvent] = {e.event_id: e for e in events}
    
    # Build graph: parent -> list of children
    children_map: dict[str, list[str]] = {e.event_id: [] for e in events}
    in_degree: dict[str, int] = {e.event_id: 0 for e in events}

    for e in events:
        if e.causation_id and e.causation_id in by_id:
            children_map[e.causation_id].append(e.event_id)
            in_degree[e.event_id] += 1

    # Queue of roots (in-degree 0)
    roots = [e for e in events if in_degree[e.event_id] == 0]
    # Deterministic sort of roots
    roots.sort(key=lambda x: (x.created_at, x.node_id, x.sequence))

    sorted_events: list[CanonicalEvent] = []
    ready = roots

    while ready:
        curr = ready.pop(0)
        sorted_events.append(curr)

        # Release children
        next_candidates = []
        for child_id in children_map[curr.event_id]:
            in_degree[child_id] -= 1
            if in_degree[child_id] == 0:
                next_candidates.append(by_id[child_id])

        if next_candidates:
            next_candidates.sort(key=lambda x: (x.created_at, x.node_id, x.sequence))
            ready.extend(next_candidates)
            ready.sort(key=lambda x: (x.created_at, x.node_id, x.sequence))

    # Any remaining cycles or disconnected items (fallback to deterministic sort)
    if len(sorted_events) < len(events):
        seen = {e.event_id for e in sorted_events}
        remaining = [e for e in events if e.event_id not in seen]
        remaining.sort(key=lambda x: (x.created_at, x.node_id, x.sequence))
        sorted_events.extend(remaining)

    return sorted_events


@dataclass
class MaterializedPosition:
    position_id: str
    symbol: str
    direction: str
    size: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    status: str = "OPEN"
    realized_pnl: float = 0.0
    opened_at: str = ""
    closed_at: str | None = None
    node_id: str = ""
    strategy_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaperTradingState:
    """Materialized projection of paper trading across all nodes."""

    cash_balance: float = 100000.0
    positions: dict[str, MaterializedPosition] = field(default_factory=dict)
    closed_trades: list[dict[str, Any]] = field(default_factory=list)
    total_trades_count: int = 0
    total_realized_pnl: float = 0.0
    trades_by_node: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash_balance": round(self.cash_balance, 2),
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "closed_trades_count": len(self.closed_trades),
            "total_trades_count": self.total_trades_count,
            "total_realized_pnl": round(self.total_realized_pnl, 2),
            "trades_by_node": self.trades_by_node,
        }


@dataclass
class KnowledgeVaultState:
    """Materialized projection of knowledge objects and evidence."""

    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    claims: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    hypotheses: dict[str, dict[str, Any]] = field(default_factory=dict)
    autopsies: dict[str, dict[str, Any]] = field(default_factory=dict)
    contributions_by_node: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources_count": len(self.sources),
            "claims_count": len(self.claims),
            "evidence_count": len(self.evidence),
            "hypotheses_count": len(self.hypotheses),
            "autopsies_count": len(self.autopsies),
            "contributions_by_node": self.contributions_by_node,
        }


@dataclass
class StrategyLeagueState:
    """Materialized projection of strategy genome progression."""

    strategies: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategies_count": len(self.strategies),
            "strategies": self.strategies,
        }


@dataclass
class CollectiveState:
    """Full deterministic materialized collective state."""

    paper_trading: PaperTradingState = field(default_factory=PaperTradingState)
    knowledge: KnowledgeVaultState = field(default_factory=KnowledgeVaultState)
    strategy_league: StrategyLeagueState = field(default_factory=StrategyLeagueState)
    total_events_reduced: int = 0
    state_sha256: str = ""

    def compute_hash(self) -> str:
        data = {
            "paper_trading": self.paper_trading.to_dict(),
            "knowledge": self.knowledge.to_dict(),
            "strategy_league": self.strategy_league.to_dict(),
            "total_events_reduced": self.total_events_reduced,
        }
        return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


class CollectiveReducer:
    """Master deterministic reducer reducing canonical events into collective state."""

    def reduce(self, events: list[CanonicalEvent]) -> CollectiveState:
        """Deterministically orders and reduces events into canonical state."""
        ordered = causal_sort_events(events)
        state = CollectiveState()

        for ev in ordered:
            self._apply_event(state, ev)
            state.total_events_reduced += 1

        state.state_sha256 = state.compute_hash()
        return state

    def _apply_event(self, state: CollectiveState, ev: CanonicalEvent) -> None:
        etype = ev.event_type
        payload = ev.payload
        node_id = ev.node_id

        # Track node contribution
        state.paper_trading.trades_by_node.setdefault(node_id, 0)
        state.knowledge.contributions_by_node.setdefault(node_id, 0)

        # --- Paper Trading Reducers ---
        if etype == CollectiveEventType.PAPER_POSITION_OPENED:
            pos_id = ev.entity_id
            pos = MaterializedPosition(
                position_id=pos_id,
                symbol=payload.get("symbol", "BTCUSDT"),
                direction=payload.get("direction", "LONG"),
                size=float(payload.get("size", 1.0)),
                entry_price=float(payload.get("entry_price", 0.0)),
                current_price=float(payload.get("entry_price", 0.0)),
                stop_loss=float(payload.get("stop_loss", 0.0)),
                take_profit=float(payload.get("take_profit", 0.0)),
                opened_at=ev.created_at,
                node_id=node_id,
                strategy_id=ev.provenance.get("strategy_id", ""),
            )
            state.paper_trading.positions[pos_id] = pos
            state.paper_trading.total_trades_count += 1
            state.paper_trading.trades_by_node[node_id] += 1

        elif etype == CollectiveEventType.PAPER_POSITION_MODIFIED:
            pos_id = ev.entity_id
            if pos_id in state.paper_trading.positions:
                pos = state.paper_trading.positions[pos_id]
                if "stop_loss" in payload:
                    pos.stop_loss = float(payload["stop_loss"])
                if "take_profit" in payload:
                    pos.take_profit = float(payload["take_profit"])

        elif etype == CollectiveEventType.PAPER_POSITION_CLOSED:
            pos_id = ev.entity_id
            if pos_id in state.paper_trading.positions:
                pos = state.paper_trading.positions[pos_id]
                exit_price = float(payload.get("exit_price", pos.current_price))
                pnl = float(payload.get("realized_pnl", 0.0))
                pos.status = "CLOSED"
                pos.current_price = exit_price
                pos.realized_pnl = pnl
                pos.closed_at = ev.created_at

                state.paper_trading.cash_balance += pnl
                state.paper_trading.total_realized_pnl += pnl
                state.paper_trading.closed_trades.append(pos.to_dict())
                del state.paper_trading.positions[pos_id]

        # --- Knowledge Reducers ---
        elif etype == CollectiveEventType.RESEARCH_SOURCE_REGISTERED:
            src_id = ev.entity_id
            state.knowledge.sources[src_id] = {
                "source_id": src_id,
                "title": payload.get("title", ""),
                "source_uri": payload.get("source_uri", ""),
                "author": payload.get("author", ""),
                "node_id": node_id,
                "registered_at": ev.created_at,
            }
            state.knowledge.contributions_by_node[node_id] += 1

        elif etype == CollectiveEventType.CLAIM_CREATED:
            claim_id = ev.entity_id
            state.knowledge.claims[claim_id] = {
                "claim_id": claim_id,
                "claim_statement": payload.get("statement", ""),
                "source_id": ev.provenance.get("source_id"),
                "confidence": payload.get("confidence", 0.0),
                "node_id": node_id,
                "created_at": ev.created_at,
            }
            state.knowledge.contributions_by_node[node_id] += 1

        elif etype == CollectiveEventType.EVIDENCE_ATTACHED:
            ev_id = ev.entity_id
            state.knowledge.evidence[ev_id] = {
                "evidence_id": ev_id,
                "claim_id": payload.get("claim_id"),
                "verdict": payload.get("verdict", "SUPPORTED"),
                "evidence_grade": payload.get("evidence_grade", 3),
                "sample_size": payload.get("sample_size", 0),
                "node_id": node_id,
                "attached_at": ev.created_at,
            }
            state.knowledge.contributions_by_node[node_id] += 1

        elif etype == CollectiveEventType.HYPOTHESIS_CREATED:
            hypo_id = ev.entity_id
            state.knowledge.hypotheses[hypo_id] = {
                "hypothesis_id": hypo_id,
                "statement": payload.get("hypothesis", ""),
                "node_id": node_id,
                "status": "ACTIVE",
            }
            state.knowledge.contributions_by_node[node_id] += 1

        elif etype == CollectiveEventType.HYPOTHESIS_REJECTED:
            hypo_id = ev.entity_id
            if hypo_id not in state.knowledge.hypotheses:
                state.knowledge.hypotheses[hypo_id] = {
                    "hypothesis_id": hypo_id,
                    "statement": payload.get("statement", ""),
                    "node_id": node_id,
                    "status": "REJECTED",
                    "rejection_reason": payload.get("reason", ""),
                }
            else:
                state.knowledge.hypotheses[hypo_id]["status"] = "REJECTED"
                state.knowledge.hypotheses[hypo_id]["rejection_reason"] = payload.get("reason", "")
            state.knowledge.contributions_by_node[node_id] += 1

        elif etype == CollectiveEventType.RESEARCH_AUTOPSY_CREATED:
            auto_id = ev.entity_id
            state.knowledge.autopsies[auto_id] = {
                "autopsy_id": auto_id,
                "target_id": payload.get("target_id"),
                "root_cause": payload.get("root_cause", ""),
                "node_id": node_id,
            }
            state.knowledge.contributions_by_node[node_id] += 1

        # --- Strategy League Reducers ---
        elif etype == CollectiveEventType.STRATEGY_CANDIDATE_CREATED:
            strat_id = ev.entity_id
            state.strategy_league.strategies[strat_id] = {
                "strategy_id": strat_id,
                "name": payload.get("name", ""),
                "quarantine_tier": payload.get("quarantine_tier", 1),
                "forward_trades": 0,
                "node_id": node_id,
            }

        elif etype == CollectiveEventType.STRATEGY_EVALUATED:
            strat_id = ev.entity_id
            if strat_id in state.strategy_league.strategies:
                s = state.strategy_league.strategies[strat_id]
                s["forward_trades"] = payload.get("forward_trades", s.get("forward_trades", 0))
                s["expectancy"] = payload.get("expectancy")
                s["sharpe"] = payload.get("sharpe")


collective_reducer = CollectiveReducer()
