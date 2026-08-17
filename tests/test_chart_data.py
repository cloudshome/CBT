"""W2 — chart zone overlays (order blocks / FVG / liquidity / sweep / range).

The roadmap's Priority-1 chart workstation: the structure data the engine
already computes (``engine/structure.MarketStructure.as_dict``) was text-only
on the chart. ``web/chart_data._zones`` turns it into JSON-safe bands/lines
the front end draws, and ``build_chart`` carries it under ``zones``.

These tests pin the transform deterministically (no market fetch): a crafted
structure payload must map 1:1 into zone bands with plain-float values, and a
payload with no structure must yield an empty-but-shaped ``zones`` dict rather
than raise.
"""
from __future__ import annotations

import numpy as np

from web.chart_data import _zones, build_chart
from tests.conftest import make_ohlcv


def _structure_payload() -> dict:
    return {
        "snapshot": {
            "structure": {
                "order_blocks": [
                    {"side": "bullish", "top": 100.0, "bottom": 99.0,
                     "tested": False, "broken": False},
                    {"side": "bearish", "top": 110.0, "bottom": 109.5,
                     "tested": True, "broken": False},
                ],
                "fvgs": [
                    {"side": "bullish", "top": 105.0, "bottom": 104.0,
                     "filled": False},
                ],
                "liquidity_above": [115.0, 118.0],
                "liquidity_below": [95.0],
                "sweep": {"side": "buyside", "level": 116.0, "recovered": True},
                "premium_discount": {"top": 112.0, "bottom": 96.0,
                                     "position": 0.7, "zone": "premium"},
            }
        }
    }


def test_zones_map_structure_to_bands():
    z = _zones(_structure_payload())
    assert len(z["order_blocks"]) == 2
    ob = z["order_blocks"][0]
    assert ob["kind"] == "order_block"
    assert ob["side"] == "bullish"
    assert ob["top"] == 100.0 and ob["bottom"] == 99.0
    assert ob["tested"] is False
    # bearish block is tested → flagged
    assert z["order_blocks"][1]["tested"] is True

    assert len(z["fvgs"]) == 1
    fvg = z["fvgs"][0]
    assert fvg["kind"] == "fvg" and fvg["side"] == "bullish"
    assert fvg["top"] == 105.0 and fvg["bottom"] == 104.0

    # liquidity above + below both present, deduped in order
    liq = {l["side"] for l in z["liquidity"]}
    assert liq == {"above", "below"}
    assert sum(1 for l in z["liquidity"] if l["side"] == "above") == 2

    assert z["sweep"]["level"] == 116.0
    assert z["sweep"]["recovered"] is True
    assert z["dealing_range"]["top"] == 112.0
    assert z["dealing_range"]["bottom"] == 96.0
    assert z["dealing_range"]["zone"] == "premium"


def test_zones_normalise_top_bottom_order():
    """A band's top/bottom are stored as (top, bottom) regardless of input."""
    z = _zones({"snapshot": {"structure": {
        "order_blocks": [{"side": "bullish", "top": 50.0, "bottom": 60.0,
                          "tested": False, "broken": False}]}}})
    assert z["order_blocks"][0]["top"] == 60.0
    assert z["order_blocks"][0]["bottom"] == 50.0


def test_zones_handle_numpy_scalars():
    """Values funnel through _num, so numpy scalars must survive to floats."""
    z = _zones({"snapshot": {"structure": {
        "order_blocks": [{"side": "bearish", "top": np.float64(200.0),
                          "bottom": np.int64(199), "tested": False,
                          "broken": False}]}}})
    assert z["order_blocks"][0]["top"] == 200.0
    assert isinstance(z["order_blocks"][0]["top"], float)


def test_zones_empty_when_no_structure():
    assert _zones(None) == {}
    z = _zones({"snapshot": {}})
    assert z == {"order_blocks": [], "fvgs": [], "liquidity": [],
                 "sweep": None, "dealing_range": None}


def test_build_chart_includes_zones_key():
    df = make_ohlcv(200)
    chart = build_chart(df, "BTCUSDT", "15m", payload=_structure_payload(),
                        limit=150)
    assert "zones" in chart
    assert len(chart["zones"]["order_blocks"]) == 2
    assert "candles" in chart and len(chart["candles"]) == 150
