# Human actions this token cannot do

Arena's GitHub App can push code to `arena/*` and open a PR.
It **cannot** change branch protection or workflow files.

Do these two in the GitHub UI. Two minutes. Then SKY's
`main` is a real stable branch.

## TODO-8 — Protect `main`

1. Open https://github.com/Azimshawon/SKY/settings/branches
2. **Add branch protection rule** → branch name `main`
3. Enable:
   - **Require a pull request before merging**
   - **Do not allow bypassing the above settings** (optional but recommended)
   - **Do not allow force pushes**
   - **Do not allow deletions**
4. After TODO-7 is live, also tick **Require status checks to pass**
   and select `Offline test suite`.

Until this is on, an Arena session (or anyone with write) can push
straight to `main` and rewrite a risk calculation.

## TODO-7 — Paste the wheel-gate job

CI is already **active** (`.github/workflows/ci.yml` runs the offline
suite). The wheel-gate *job* is not in that file because the token
was refused when it tried to edit it.

1. Open https://github.com/Azimshawon/SKY/edit/main/.github/workflows/ci.yml
   (or edit it in a tiny follow-up PR from the GitHub UI)
2. Append the job from
   [`docs/wheel-gate-job.yml`](./wheel-gate-job.yml)
   under the existing `jobs:` map (same indent as `test:`).
3. Commit on `main` from the UI, or via a one-file PR.

Local equivalent, no GitHub needed:

```bash
python ci/wheel_gate.py            # build + duplicate-entry check
python ci/wheel_gate.py --install  # also smoke-test a clean venv
```

## Do not do next

- Do not install OpenHands, Dify, or LibreChat into this repo.
- Do not start TODO-9 / TODO-10 until
  `python main.py agent ask "am i ready for micro?"` is READY.
