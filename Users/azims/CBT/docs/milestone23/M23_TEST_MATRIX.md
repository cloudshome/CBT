# Milestone 23 Test Matrix & Traceability Scorecard

**System:** SKY / Crypto Brain Terminal (CBT)  
**Milestone:** 23  
**Classification:** Adversarial Validation & Test Gate Traceability  

---

## 1. Traceability Across the 8 Acceptance Gates

| Gate ID | Target Acceptance Gate | Test Class in `test_milestone23_campaign_orchestrator.py` | Verification Method |
|:---:|:---|:---|:---|
| **Gate 1** | **Time Accounting & Partitioning** | `TestTimeAccountingAndPartitioning` | Simulates multi-hour intervals with pauses/faults; verifies $H_{\text{elapsed}} = H_{\text{qualified}} + H_{\text{disqualified}}$ within $10^{-6}\text{h}$. |
| **Gate 2** | **Fencing Token Lease Protection** | `TestFencingTokenLeaseProtection` | Spawns two supervisor instances; advances fencing token on second; asserts first fails closed on next operation with `StaleLeaseFencingError`. |
| **Gate 3** | **Safe Pause & Resume Semantics** | `TestSafePauseAndResumeSemantics` | Triggers pause mid-flight; asserts in-flight slices drain cleanly; asserts $Q_{\text{unresolved}} == 0$ on resume before advancing. |
| **Gate 4** | **Rate Limit Emergency Capacity Under Load** | `TestRateGovernorEmergencyCapacity` | Satures normal and urgent rate-limit tiers to 100% capacity; asserts emergency cancel token acquires immediately without delay. |
| **Gate 5** | **Regime Signal Firewall** | `TestRegimeCoveragePolicyFirewall` | Ingests mock high-volatility regime data; asserts output is strictly a `FlightManifest` with test parameters and 0 directional positioning signals. |
| **Gate 6** | **Cockpit Sequence Monotonicity & Watermark** | `TestCockpitTelemetryAndWatermarking` | Simulates packet drops and stale heartbeats; verifies `telemetry_seq` increments monotonically and stale flag activates at $>3000\text{ms}$. |
| **Gate 7** | **Chained SHA-256 Forensic Audit Bundle** | `TestChainedForensicAuditBundle` | Generates consecutive 1-hour interval records; verifies SHA-256 hash chaining; mutates past record and asserts verification fails closed. |
| **Gate 8** | **Milestone 18 Certification Invariant** | `TestM18SurfacePreservation` | Verifies all 14 M18 certified files are 100% untouched and matches certified test identity hash. |

---

## 2. Test Execution Command

```powershell
.venv\Scripts\pytest tests/execution/test_milestone23_campaign_orchestrator.py -v
```
