# M35 Ubuntu Paper-Shadow Runtime Proof & Telemetry Audit
**Document:** `docs/M35_UBUNTU_RUNTIME_PROOF.md`  
**Classification:** Distributed Operations & Runtime Verification Audit  
**Authority:** Paper-Trading Reliability Engineer  
**Date:** 2026-11-04  
**Audit Source:** [`research/m35_runtime_snapshot.json`](file:///c:/Users/azims/CBT/research/m35_runtime_snapshot.json)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary & Epistemic Honesty

In M34, the report stated that the three candidate strategies were actively running 24/7 in paper-shadow mode on the Ubuntu server. 

**The operator rightly challenged this claim:**
- *Initializing a genesis block in a local Git repository is NOT proof that an active operating-system daemon is running.*
- *The Windows workspace has no live telemetry verifying the Ubuntu PID, uptime, or WebSocket connection.*

Under SKY AGENTS.md Directive 4:
> **"NEVER claim code was 'tested' or 'working' unless you actually executed the test command and inspected the output."**
> **"If data is missing or untested, state explicitly: NOT YET VALIDATED or INSUFFICIENT DATA."**

### Official Classification:
$$\mathbf{Paper\text{-}Shadow\ Deployment:\ Reported,\ Runtime\ Verification\ PENDING}$$

---

## 2. Forensic Audit of Local Host Evidence

We audited all local runtime artifacts in `C:\Users\azims\CBT`:
1. **Prospective Ledger Status:**
   - File [`research/live_paper_practice_manifest.jsonl`](file:///c:/Users/azims/CBT/research/live_paper_practice_manifest.jsonl) exists.
   - Contains exactly one event: `GENESIS_PAPER_SHADOW_LEDGER` timestamped `2026-11-04T06:55:31Z`.
   - **Zero subsequent forward trade events have been logged yet.**
2. **Local Daemon State:**
   - No local background Python daemon is currently executing `app.py --mode=paper-shadow` on the Windows host.
   - The Windows session was previously running background test suites (`system_preflight.py`), which were cancelled to prevent database locks.
3. **Remote Ubuntu Connectivity:**
   - The Windows sandbox lacks an active SSH tunnel, remote socket connection, or FHS access to `/etc/sky/sky.env` on the Ubuntu host.
   - The live systemd status of `sky-paper.service` on Ubuntu cannot be polled directly from this Windows shell.

---

## 3. Ubuntu Host Inspection Protocol (Operator Verification)

To transition Paper-Shadow Deployment from `RUNTIME_VERIFICATION_PENDING` to `VERIFIED_ACTIVE`, the operator must run the following verification commands directly on the Ubuntu server terminal:

```bash
# 1. Check systemd service status
sudo systemctl status sky-paper.service

# 2. Inspect active process table for python paper worker
ps aux | grep -E "app.py|paper" | grep -v grep

# 3. View live journal logs
journalctl -u sky-paper.service -n 50 --no-pager

# 4. Verify latest closed candle reconciliation and WebSocket connection
tail -n 30 /var/log/sky/paper_shadow.log

# 5. Verify live ledger export
head -n 5 ~/CBT/research/live_paper_practice_manifest.jsonl
```

### Required Evidence to Declare Runtime Active:
- Process PID $> 0$
- System uptime $> 0\text{ hours}$
- WebSocket status: `CONNECTED (binance perp)`
- Last closed candle: timestamp matches latest completed exchange hour
- Zero unhandled exceptions or restart loops.

Until this telemetry is verified and attached, the operational status remains **`RUNTIME_VERIFICATION_PENDING`**.
