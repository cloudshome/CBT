"""data/provenance.py — P12.11: where a graded row's price actually came from.

The learning loop had one dimension too few. Every decided row was filed under
``plan_type[::regime]`` and nothing else, so two rows produced by completely
different price series — Binance BTCUSDT perp candles, and Dukascopy XAUUSD
**bid** candles imported for research — were pooled into the same calibration
entry. A research backtest on a venue the desk does not trade could therefore
recalibrate the confidence multiplier used on the live book. That was
Dukascopy blocker #3, and it is the reason ``--save`` was prohibited for the
XAU adapter (`docs/DUKASCOPY_XAU_ADAPTER.md`).

This module supplies the missing dimension: a **source key** built from the
three facts that decide whether two price series are the same market.

    exchange   binance | bybit | dukascopy | ...   (who printed the price)
    market     spot | perp                          (which book)
    price_type (blank) | bid | ask                  (which side of the spread)

Design rules (deliberate — do not "simplify" away):

* **The canonical live series has an empty key.** ``binance`` / ``spot`` /
  blank price type normalises to ``""``. That is what makes P12.11 additive:
  every pre-existing calibration key, every legacy row whose provenance
  columns are NULL, and every live Binance scan produce byte-identical keys
  to the ones the engine used before this module existed.
* **Unknown is not a guess.** Missing fields fall back to the canonical
  default rather than inventing a venue, because all history predating the
  provenance columns *is* the canonical Binance series.
* **One parser, one formatter.** ``source_key()`` and ``parse_source_key()``
  round-trip, so the CLI, HTTP, MCP and DB layers cannot disagree about what
  ``dukascopy:spot:bid`` means (invariant #10).
"""
from __future__ import annotations

from typing import Optional

# The canonical live series the desk actually trades. Rows carrying this
# provenance — and rows predating P12.11, whose columns are NULL — key to "".
CANONICAL_EXCHANGE = "binance"
CANONICAL_MARKET = "spot"
CANONICAL_PRICE_TYPE = ""

#: Source key of the canonical live series (deliberately the empty string).
LIVE_SOURCE_KEY = ""

#: Separator inside a source key: ``exchange:market:price_type``.
FIELD_SEP = ":"

#: Separator that attaches a source key to a calibration key.
KEY_SEP = "@"

#: Price types that mean "one side of the spread, not a tradeable round trip".
ONE_SIDED_PRICE_TYPES = frozenset({"bid", "ask"})


def _clean(value: Optional[str]) -> str:
    """Normalise one provenance field: strip, lowercase, empty when unknown."""
    if value is None:
        return ""
    return str(value).strip().lower()


def normalize(exchange: Optional[str] = None, market: Optional[str] = None,
              price_type: Optional[str] = None) -> tuple[str, str, str]:
    """Normalise a provenance triple, defaulting to the canonical live series.

    ``None``/blank exchange or market means "the row predates provenance
    tracking", and every such row belongs to the canonical Binance spot
    series — that is a fact about our history, not an assumption.
    """
    ex = _clean(exchange) or CANONICAL_EXCHANGE
    mk = _clean(market) or CANONICAL_MARKET
    pt = _clean(price_type)
    if pt in ("mid", "last", "close", "ohlc", "none"):
        # A two-sided/last-traded series is the canonical shape; only an
        # explicitly one-sided import needs to be distinguished.
        pt = ""
    return ex, mk, pt


def source_key(exchange: Optional[str] = None, market: Optional[str] = None,
               price_type: Optional[str] = None) -> str:
    """``exchange:market[:price_type]`` — or ``""`` for the canonical series.

    >>> source_key()                                    # live Binance spot
    ''
    >>> source_key("binance", "spot", "")
    ''
    >>> source_key("binance", "perp")
    'binance:perp'
    >>> source_key("dukascopy", "spot", "bid")
    'dukascopy:spot:bid'
    """
    ex, mk, pt = normalize(exchange, market, price_type)
    if (ex, mk, pt) == (CANONICAL_EXCHANGE, CANONICAL_MARKET, CANONICAL_PRICE_TYPE):
        return LIVE_SOURCE_KEY
    return FIELD_SEP.join([ex, mk] + ([pt] if pt else []))


def parse_source_key(key: Optional[str]) -> tuple[str, str, str]:
    """Inverse of `source_key` — always returns a normalised triple."""
    raw = _clean(key)
    if not raw:
        return normalize()
    parts = raw.split(FIELD_SEP)
    ex = parts[0] if len(parts) > 0 else ""
    mk = parts[1] if len(parts) > 1 else ""
    pt = parts[2] if len(parts) > 2 else ""
    return normalize(ex, mk, pt)


def is_canonical(key: Optional[str]) -> bool:
    """True when this source key is the live series the desk trades."""
    return source_key(*parse_source_key(key)) == LIVE_SOURCE_KEY


def is_one_sided(key: Optional[str]) -> bool:
    """True when the series is bid-only or ask-only (not a round trip).

    A bid-only book cannot be entered and exited at the printed price, so it
    is research evidence even when its expectancy looks excellent.
    """
    _, _, price_type = parse_source_key(key)
    return price_type in ONE_SIDED_PRICE_TYPES


def describe_source(key: Optional[str]) -> str:
    """Human label for a source key, for CLI/report lines."""
    ex, mk, pt = parse_source_key(key)
    if source_key(ex, mk, pt) == LIVE_SOURCE_KEY:
        return f"{ex} {mk} (canonical live series)"
    label = f"{ex} {mk}"
    if pt:
        label += f" {pt}-only"
    return label


def split_profile_key(key: str) -> tuple[str, str, str]:
    """Split a calibration key into ``(plan_type, regime, source_key)``.

    Accepts every key shape SKY has ever written, so a profile saved before
    P12.11 still parses:

    >>> split_profile_key("Buy Pullback")
    ('Buy Pullback', '', '')
    >>> split_profile_key("Buy Pullback::TREND_UP")
    ('Buy Pullback', 'TREND_UP', '')
    >>> split_profile_key("Buy Pullback::TREND_UP@dukascopy:spot:bid")
    ('Buy Pullback', 'TREND_UP', 'dukascopy:spot:bid')
    """
    text = key or ""
    base, sep, src = text.partition(KEY_SEP)
    plan_type, _, regime = base.partition("::")
    return plan_type, regime, (src if sep else "")


def provenance_of_frame(df, exchange: Optional[str] = None,
                        market: Optional[str] = None) -> tuple[str, str, str]:
    """Read provenance off a candle frame produced by the store or a client.

    The store stamps ``exchange`` / ``market`` / ``price_type`` onto every
    partition (P10.1, extended by the Dukascopy adapter), so the honest answer
    is the one carried by the data itself; the caller's arguments are only a
    fallback for clients that do not stamp anything (the live REST client).
    """
    attrs = getattr(df, "attrs", {}) or {}
    ex = attrs.get("exchange") or exchange
    mk = attrs.get("market") or market
    pt = attrs.get("price_type") or ""
    if not pt and df is not None and getattr(df, "empty", True) is False:
        try:
            if "price_type" in df.columns:
                vals = {str(v).strip().lower() for v in df["price_type"].dropna().unique()}
                vals.discard("")
                # A mixed-side series is a bug the importer already refuses;
                # if one ever appears, do not silently pick a side.
                if len(vals) == 1:
                    pt = vals.pop()
        except Exception:  # pragma: no cover - never break a backtest on this
            pt = ""
    return normalize(ex, mk, pt)
