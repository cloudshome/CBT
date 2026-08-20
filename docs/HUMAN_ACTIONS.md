# Human/admin actions

Arena's GitHub integration can push session branches and open pull requests.
It cannot read or change repository branch-protection settings in this repo
(the API returns HTTP 403), so one admin check remains.

## TODO-8 — Verify and protect `main`

1. Open https://github.com/Azimshawon/SKY/settings/branches
2. Inspect or add the rule/ruleset for `main`.
3. Require:
   - a pull request before merging;
   - both status checks: **Offline test suite** and **Wheel gate**;
   - no force pushes;
   - no branch deletion;
   - no bypass (recommended).

The integration cannot tell whether this is already configured. Treat TODO-8
as **unverified** until a repository admin confirms it in the GitHub UI.

## TODO-7 — CI wheel-gate · ✅ complete

The root `.github/workflows/ci.yml` contains both the offline suite and wheel
gate. GitHub Actions run `31907327643` passed both jobs on merged P12.12 at
commit `5345e9e` on `main`. No workflow copy/paste action remains.

Local equivalents:

```bash
python ci/wheel_gate.py
python ci/wheel_gate.py --install
```

## NEW (2026-08-20) — CI Node-20 deprecation: bump the active workflow · 🔧 human action

GitHub runners now deprecate Node-20 actions; the active workflow's
`actions/checkout@v4` and `actions/setup-python@v5` are force-run on Node 24
with a deprecation annotation. The current Node-24 majors are
`actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7`
(all verified `using: node24` via the GitHub API on 2026-08-20).

**The integration cannot perform this bump itself** — the GitHub App lacks the
`workflows` permission, so pushes touching `.github/workflows/ci.yml` are
rejected. A repository admin should edit `.github/workflows/ci.yml` (or use
the GitHub UI) and replace `checkout@v4` → `checkout@v7` and
`setup-python@v5` → `setup-python@v7` in both jobs. Until then CI stays green;
it only carries the annotation.

The dormant `ci/release.workflow.yml` spec (not under `.github/workflows/`,
therefore editable by the integration) is already bumped to the same majors.

## Do not do next

- Do not install OpenHands, Dify, or LibreChat into this repo.
- Do not start TODO-9 / TODO-10 until
  `python main.py agent ask "am i ready for micro?"` is READY.
- Do not build order placement while the graduation and explicit-approval
  gates remain open.
