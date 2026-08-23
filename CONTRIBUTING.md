# Contributing to SKY

SKY uses GitHub as its source of truth. All changes arrive through a pull
request from a focused branch; `main` is production-ready and is not a shared
editing branch.

## Choose the right lane

- **Antigravity:** architecture, implementation, integration, debugging, and
  browser testing.
- **AI Studio:** isolated Gemini/UX experiments. Use `experiment/*` or
  `ai/*`; promote only reviewed, tested code into a production branch.
- **Jules:** bounded asynchronous work from an Issue, such as tests,
  documentation, a dependency update, or a reproducible bug fix.

Never have two tools edit the same branch at the same time. Open a separate PR
for each concern and merge only after CI and human review.

## Branches and commits

Use descriptive branches such as `feature/<short-name>`, `fix/<short-name>`,
`experiment/<short-name>`, or `docs/<short-name>`. Keep commits small and
explain the user-visible reason in the commit message.

## Pull request checklist

1. Link the issue or explain the problem and success criteria.
2. Describe the approach, safety impact, and any compatibility implications.
3. Add or update tests for behavior changes.
4. Run the validation commands in `AGENTS.md` and report their results.
5. Confirm no secrets, databases, market-data stores, or generated artifacts
   are included.
6. Update docs when an API, CLI, configuration, or operating rule changes.
7. Request human review. A green CI run does not authorize a risk-policy change.

## Safety boundary

This project is read-only by design. Do not add exchange-order placement,
secret handling, or a bypass around approval, risk, evidence, journal, or data
quality gates without an explicit reviewed design decision. See `SECURITY.md`
and `AGENTS.md`.
