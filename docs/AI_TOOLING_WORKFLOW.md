# AI tooling workflow

This repository supports a simple, reviewable collaboration model for AI
Studio, Antigravity, and Jules. **GitHub is the single source of truth.** The
tools are workers with different jobs, not three copies of the application.

```text
You define the issue
        |
        v
GitHub issue / focused branch
   |             |             |
AI Studio    Antigravity     Jules
prototype    implement       bounded async task
   |             |             |
   +-------------+-------------+
                 v
             pull request
                 |
          CI + human review
                 |
                main
```

## Responsibilities

| Tool | Use it for | Output |
| --- | --- | --- |
| Antigravity | Architecture, implementation, integration, debugging, browser QA | Focused branch and PR |
| AI Studio | Gemini prompts, structured output, AI UX, and isolated prototypes | `experiment/*` or `ai/*` branch and a reviewable prototype |
| Jules | Tests, docs, dependency review, reproducible fixes, and other bounded jobs | Issue-linked PR with test results |
| GitHub Actions | Compile, tests, build/syntax, and security checks | Required mechanical gate |
| Human owner | Product direction, risk policy, architecture, and merge decision | Final review and approval |

## Safe handoff

1. Create or update an Issue with scope, acceptance criteria, files in scope,
   constraints, and validation commands.
2. Give each tool its own branch. Do not let AI Studio and Antigravity edit the
   same branch concurrently.
3. Ask for a plan first for architecture or risk-sensitive work. Prototypes
   must be reviewed for secrets, error handling, cost, maintainability, and
   tests before productionizing.
4. Require every worker to run offline validation and report failures honestly.
5. Review the diff, CI results, and safety impact before merging.

## Useful task prompts

### Planning

> Read `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, and the relevant roadmap.
> Propose a small plan and list risks. Do not modify files yet.

### Jules test task

> Add regression tests for Issue #N. Do not change production behavior or schema.
> Keep tests offline and deterministic. Run the targeted tests and full suite;
> open a PR with the results.

### AI Studio prototype handoff

> This is an isolated prototype, not production code. Document the prompt,
> model assumptions, input/output schema, failure cases, and required secrets.
> Do not commit credentials or claim the prototype proves trading performance.

## Non-negotiable boundaries

- Never push directly to `main`.
- Never add live exchange-order placement.
- Never bypass approval, risk, evidence, journal, authentication, CSRF, or data
  quality gates.
- Never commit secrets or generated market-data stores.
