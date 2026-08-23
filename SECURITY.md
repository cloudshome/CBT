# Security policy

## Scope

SKY is a single-user trading research and paper-trading workstation. It handles
market data, local learning history, optional provider integrations, and a web
workstation. It is read-only with respect to exchanges: no code in this project
should place a live order.

## Report a vulnerability

Please do not disclose credentials, tokens, private URLs, or a working exploit
in a public issue. Report security concerns privately through the repository's
GitHub security reporting channel (Security tab) or to the repository owner,
including the affected commit, impact, reproduction steps, and a safe contact
method.

If private reporting is unavailable, open an issue with only a minimal,
non-sensitive description and request a private follow-up.

## Security rules for contributors and agents

- Never commit `.env`, secrets, tokens, cookies, personal data, SQLite files,
  collected market data, or production configuration.
- Use `.env.example` for names and safe placeholder values only.
- Validate and constrain all external input, including LLM output and webhook
  payloads. Keep source provenance and fail closed on invalid data.
- Preserve authentication, CSRF, role, rate-limit, audit, idempotency, risk,
  and data-quality controls when changing the web/API layers.
- Do not introduce live-order APIs or code paths that evade human approval.
- Keep tests offline and deterministic; use demo transports and sample data.
