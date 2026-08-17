# Cactus Needle 2 recommendation — review & decision

> **Status:** decided for the current SKY architecture. No runtime change and
> no `cactus-needle` dependency.
> **Date:** 2026-08-17
> **Reviewed against:** the supplied crypto/trading note, the official Needle 2
> page and repository as of 2026-08-17, and SKY v2.29.0 (`mcp_server.py`,
> `ai/mcp_server.py`, `ARCHITECTURE.md`, and the paper-only safety contract).
>
> **One-line verdict:** the role proposed for Needle is sound, but SKY already
> has that boundary as two typed MCP servers. Needle is a possible **external
> read-only MCP client** if a real edge-device requirement appears; it is not
> P0/P1 infrastructure, not a strategy brain, and not an execution authority.
> Do not install it now.

This document preserves the useful thought without turning an interesting
model into an unmeasured dependency. A future session proposing an integration
must satisfy **N1–N8** below rather than starting from the marketing numbers.

---

## 1. What the recommendation gets right

The central separation is correct:

```text
LLM/router proposes a typed call
        ↓
deterministic SKY code computes the answer
        ↓
risk and permission boundaries decide what is allowed
        ↓
human controls all mutation; SKY places no exchange orders
```

Needle 2 is explicitly a narrow tool-calling and structured-extraction model,
not an open-ended market analyst. The current upstream describes a 45M
parameter, 14 MB CQ2-bit artifact, about 28 MB bounded session RAM, a
256-token sliding window, schema-constrained decoding, tool retrieval, and a
learned confidence score. Those are attractive properties for a Raspberry Pi,
phone, wearable, or offline controller.

The note is also right about deterministic ownership:

- indicators, position sizing, expectancy, and scorecards belong in code;
- market interpretation and research do not belong in a 45M tool router;
- confidence may trigger abstention/escalation, but may never bypass risk;
- direct `AI → exchange` is forbidden.

SKY already implements those principles more narrowly than the proposed
30–50-tool diagram.

---

## 2. What SKY already has (do not rebuild)

| Proposed Needle role | Existing SKY boundary |
|---|---|
| typed tool catalogue | `mcp_server.ALLOWED_TOOLS` and `ai/mcp_server.py::TOOLS` JSON schemas |
| tool selection client | any external MCP-capable agent; SKY does not need to own the client |
| deterministic market analytics | `engine/`, `data/`, `brain/` library functions |
| expectancy/backtest orchestration | read-only `scorecard`, `ask`, and SDK stats/learning tools |
| health and confidence handoff | `readiness`, `health`, `desk_status`, and `loop_health` |
| permission control | MCP allowlists; the root server exposes no approval/order path |
| risk authority | `brain/risk_gate.py`, never an LLM confidence score |
| paper workflow | dashboard/CLI human actions and `data/paper_trading.py`; no exchange order code |

The MCP catalogues are intentionally **small capability boundaries**, not a
list of every Python function. Turning every indicator into a separately
routable tool would increase ambiguity, latency, maintenance, and permission
surface while bypassing SKY's composed source-of-truth reports. “30–50 tools”
is therefore not a goal.

Needle's convenient `run()` API can execute a selected Python function. That
is acceptable for a weather demo but is the wrong trust boundary inside SKY.
If Needle is ever evaluated, it must call the existing MCP boundary (or a
schema-identical read-only adapter), never decorate arbitrary SKY functions.

---

## 3. Corrections and cautions to the supplied note

1. **The current model is Needle 2, 45M parameters.** The linked repository's
   older description/model card may still appear in search snippets. Pin the
   exact upstream version and model artifact in any experiment; do not mix
   Needle 1/2 figures.
2. **Published benchmark accuracy is not trading-domain accuracy.** Upstream
   reports strict exact-match results on Mobile Actions, DroidCall,
   Seal-Tools, and BFCL. None measures symbols, timeframes, source provenance,
   position sizing, or false trading actions.
3. **Small is not the same as safe.** Schema-constrained JSON prevents broken
   structure, not a valid-but-wrong symbol, timeframe, tool, or argument.
4. **Confidence is routing metadata, not authorization.** A high model score
   cannot open the risk gate, approve a signal, mutate the paper book, or
   place an order. Low confidence should abstain or escalate.
5. **Do not accept an arbitrary examples-per-tool number as evidence.** The
   current upstream supports JSONL fine-tuning and held-out validation, but
   dataset size must follow measured error coverage, deduplication, and a
   genuinely sealed test split. Synthetic paraphrase volume is not proof.
6. **Low latency is not currently SKY's bottleneck.** Data freshness, real
   canonical paper evidence, and graduation remain the bottlenecks. Replacing
   an MCP client cannot improve expectancy.

---

## 4. Decisions N1–N8

| ID | Question | Decision | Binding consequence |
|---|---|---|---|
| **N1** | Add `cactus-needle` to SKY now? | **No.** | No runtime/dev dependency, vendored binary, model blob, startup download, or cache committed to this repository. |
| **N2** | Make Needle SKY's analyst, strategy selector, calculator, or trading brain? | **No.** | `engine/`, `data/`, `brain/`, and the optional larger narrative model keep their present responsibilities. Deterministic code owns numbers. |
| **N3** | Create a new `SKY-NODE` service or 30–50 fine-grained tools now? | **No.** | The existing MCP schemas are the candidate interface. Tool count follows user jobs and least privilege, never a target number. |
| **N4** | Expose paper/live order, approve, close, or gate-override tools to Needle? | **No.** | Root MCP remains read-only. No signed endpoints or exchange credentials. Human mutation remains CLI/dashboard-only. |
| **N5** | Keep the local-router idea? | **Yes, parked and conditional.** | It becomes eligible only for a concrete offline/privacy/edge-device deployment where measured resource or latency limits make the current client unsuitable. |
| **N6** | Use confidence-based escalation? | **Keep the pattern, not the authority.** | Threshold policy is `execute read-only call / ask for clarification / escalate / abstain`; every call still passes the MCP allowlist and normal validation. |
| **N7** | Fine-tune on crypto commands immediately? | **No.** | First benchmark the untouched pinned model against a held-out SKY corpus. Fine-tune only if errors cluster in repairable language mappings; never train on the sealed test set. |
| **N8** | Let a successful router unlock trading or count toward graduation? | **No.** | Router quality and strategy quality are separate scoreboards. Graduation remains canonical live paper evidence net of costs plus human discipline. |

---

## 5. The only acceptable pilot

A pilot is justified only when an operator names a target such as “offline
Raspberry Pi 5 voice controller” and supplies a measurable constraint. It
must live outside SKY's default runtime and proceed in this order:

1. **Freeze the boundary.** Export only the existing read-only MCP tool
   schemas. Do not expose Python internals or dashboard mutation endpoints.
2. **Pin provenance.** Record Needle package version, upstream commit, model
   artifact hash, engine version, target hardware, and license. Downloads are
   an explicit setup step, never import-time behavior.
3. **Build a domain evaluation set.** Include paraphrases, aliases, malformed
   numbers, missing arguments, ambiguous timeframes, unsupported symbols,
   prompt-injection attempts, requests for mutation, and off-topic requests.
   Deduplicate by intent before splitting train/validation/test.
4. **Baseline before tuning.** Compare Needle with the current external MCP
   client and a deterministic command parser where applicable.
5. **Score the router, not P&L.** At minimum:
   - exact tool-name accuracy;
   - exact/typed argument accuracy;
   - ordered multi-call exact match;
   - invalid and missing-argument rates;
   - wrong-symbol and wrong-timeframe rates;
   - abstention/escalation precision and recall;
   - false-action rate on forbidden/mutation requests;
   - p50/p95 latency, peak RAM, and cold-start time on target hardware.
6. **Fail closed.** A malformed, low-confidence, unsupported, or policy-
   violating request returns no call. **Forbidden-action false accepts must be
   zero in the sealed suite.**
7. **Shadow mode only.** Log proposed calls beside the current path; execute no
   mutation. Review disagreements manually before considering read-only use.

Passing this pilot would permit an optional read-only client. It would not
permit order execution, change the graduation bar, or make Needle part of the
strategy engine.

---

## 6. Final architecture

```text
optional edge UI / voice
        ↓
Needle 2 (only if N5 trigger exists)
  select + extract + confidence
        ↓
existing read-only MCP permission map
        ↓
SKY deterministic analytics / reports
        ↓
human sees evidence
        ↓
CLI/dashboard mutation → risk gate → paper runner

NO path: Needle → approval → exchange
```

The supplied thought is therefore **kept as a deployment option and rejected
as current infrastructure work**. SKY's highest-value next work remains
operating the real canonical paper-to-graduation loop, not replacing the tool
client around a boundary that already exists.

---

## Sources reviewed

- Cactus Compute, “Needle 2 — The 14 MB Agentic LLM for Tiny Devices”:
  <https://cactuscompute.com/needle>
- `cactus-compute/needle`, current Needle 2 Python inference/fine-tuning repo:
  <https://github.com/cactus-compute/needle>
- Needle 2 weights linked by upstream:
  <https://huggingface.co/Cactus-Compute/needle2>
