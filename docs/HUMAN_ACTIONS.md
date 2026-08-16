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

## Do not do next

- Do not install OpenHands, Dify, or LibreChat into this repo.
- Do not start TODO-9 / TODO-10 until
  `python main.py agent ask "am i ready for micro?"` is READY.
- Do not build order placement while the graduation and explicit-approval
  gates remain open.
