# Market calendars (P12.9)

## The problem

Every data-quality check in SKY was written for crypto, where the market never
closes. Under that assumption two very different events are indistinguishable:

- **the venue was shut** (Saturday, spot gold), and
- **our data collection broke** (missing candles).

That is harmless while every series is Binance. It is not harmless for the
Dukascopy XAUUSD research book added in v2.19.0: a correct, complete week of
spot gold contains ~53 hours of scheduled closure, which the crypto-first logic
read as a 30%+ gap fraction and an unusably stale feed — enough to
**quarantine a perfectly healthy series** and roll the whole desk to *not
ready*.

`SESSION_STATE.md` recorded this as the first of three blockers before any
Dukascopy-derived calibration. This is that blocker closed.

## The model

`data/calendar.py` supplies one small protocol:

```python
class MarketCalendar(Protocol):
    name: str
    always_open: bool

    def is_open(self, ts_ms: int) -> bool: ...
    def closed_intervals(self, start_ms: int, end_ms: int) -> list[tuple[int, int]]: ...
```

Two implementations ship:

| calendar | venue | rule |
|---|---|---|
| `crypto-24x7` | Binance / Bybit, all crypto incl. `PAXGUSDT` | always open |
| `xau-otc` | Dukascopy `XAUUSD` | the OTC gold week below |

### The gold week (America/New_York wall time, DST-aware)

```text
weekly open    Sunday    18:00 ET
weekly close   Friday    17:00 ET
daily break    17:00–18:00 ET, Monday–Thursday
holidays       1 January, 25 December (full ET day)
```

Boundaries are *local* ET times resolved through `zoneinfo`, so the UTC offset
moves with daylight saving exactly as the real market does — the Friday close
is 21:00 UTC in July and 22:00 UTC in January.

Partial/early closes are deliberately **not** modelled. An unmodelled early
close surfaces as a real gap (safe, visible); an over-broad holiday list would
silently swallow one (unsafe).

## Safety direction

The calendar can only ever stop a *scheduled closure* being mistaken for a gap.
It is wired so that it can never weaken an existing check:

1. **Opt-in by venue, never by guess.** `calendar_for()` returns `crypto-24x7`
   unless the series is explicitly OTC gold (`dukascopy` + an XAU symbol). An
   unknown exchange, an unknown symbol, or an empty identity all default to
   24/7. Binance `PAXGUSDT` — the live XAU proxy — is a genuinely 24/7 token
   and keeps crypto rules.
2. **Crypto numbers are byte-identical.** `detect_gaps(frame, tf)` and
   `detect_gaps(frame, tf, CRYPTO)` return the same list; `checks_on_frame`
   takes the pre-P12.9 branch whenever `always_open` is true.
3. **Real holes still fail.** A missing bar *inside* a gold session is still a
   gap, a series stale during open hours is still quarantined, and corrupt OHLC
   is still quarantined regardless of calendar.

## What became calendar-aware

| surface | change |
|---|---|
| `data/gaps.detect_gaps(frame, tf, calendar=None)` | a span that is entirely a scheduled closure is not a gap; a partial one counts only the OPENs the venue owed |
| `data/quality.checks_on_frame(..., calendar=None)` | `expected` counts trading bars, `age_mult` counts **trading** bars (a shut market cannot age a series), plus new `calendar` / `market_open` / `closed_bars` fields |
| `data/quality.series_health` / `series_item` | resolve the calendar from the series identity automatically; the readiness pillar inherits it |
| `data/quality.verdict_for` | staleness detail reads `N trading bars` on a session venue; a clean, shut series reports `market closed — clean` instead of a false alarm |
| `data/backfill.backfill_from_csv` | the import report carries `calendar` and `closed_session_bars`, and `gaps_found` no longer counts the weekend |
| `main.py backfill --from-csv` | `gaps_remaining` is calendar-aware; the human output prints the calendar and skipped closed-session bars |

## Counting helpers

```python
expected_bars(start_ms, end_ms, step_ms, calendar)  # OPENs the venue owed
open_bars_between(start_ms, end_ms, step_ms, cal)  # staleness, in trading bars
closed_bar_count(start_ms, end_ms, step_ms, cal)  # OPENs skipped by closure
split_by_session(timestamps, calendar)  # (during_session, while_closed)
```

## CLI

```bash
# Is spot gold open right now, and what calendar governs it?
python main.py calendar

# Evaluate a specific instant (UTC epoch ms) as JSON
python main.py calendar --at 1783684800000 --json

# Inspect a stored series in trading time
python main.py calendar --symbol XAUUSD --tf 1h --series

# Crypto is explicit too, and always open
python main.py calendar --exchange binance --market perp --symbol BTCUSDT
```

`--calendar crypto-24x7|xau-otc` forces a calendar for an ad-hoc check;
`--root` points at an alternate store.

## Still open before Dukascopy calibration

Closing the calendar blocker does **not** open the risk gate. Two of the three
blockers recorded in `docs/DUKASCOPY_XAU_ADAPTER.md` remain:

1. **Bid/ask spread and XAU-specific net costs.** The generic crypto cost model
   is not evidence of gold execution cost.
2. **Source provenance in saved calibration keys.** Until a learning key records
   which candle series produced it, `backtest --save` on the Dukascopy book
   could silently recalibrate the live PAXG proxy.

Until both are closed, Dukascopy XAU stays research-only.
