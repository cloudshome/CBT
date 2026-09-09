# LOCAL_SYNC.md — Keeping a local clone aligned with GitHub

**Applies to:** `cloudshome/CTB` (https://github.com/cloudshome/CTB.git)
**Default branch:** `main` · Current tip reference used in examples: `5910832`

This note is for anyone cloning CTB onto **another machine** (your own PC) and
wanting that clone to stay in lockstep with GitHub and with any sandbox clone.
GitHub is the source of truth — a local clone is always a mirror, never a
source.

---

## 1. One-time clone

```bash
git clone https://github.com/cloudshome/CTB.git
cd CTB
```

## 2. Make `git fetch` see ALL branches (recommended config)

By default this repo only fetches `main`, which means feature/arena/working
branches exist on GitHub but have **no** remote-tracking ref locally (e.g.
`origin/arena/01a087d1-ctb` is "unknown revision" until you fix this). Set the
fetch refspec to mirror every branch:

```bash
git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
git fetch --prune origin
```

Now `git for-each-ref refs/remotes/origin` shows every branch, and your working
branch correctly tracks its upstream.

## 3. Daily sync of the working branch

```bash
git fetch --prune origin
git checkout arena/01a087d1-ctb   # or the branch you work on
git pull --ff-only origin arena/01a087d1-ctb
```

## 4. Keep `main` current too

The repo's `main` moves frequently. Pull it with a fast-forward so your local
`main` matches GitHub:

```bash
git checkout main
git pull --ff-only origin main
```

> `--ff-only` is deliberate: it refuses to merge when you have local commits on
> that branch, which prevents accidental divergence. If it fails, you have local
> work to handle first.

## 5. Verify alignment

```bash
git status -sb
git rev-parse HEAD origin/arena/01a087d1-ctb   # both should print the same SHA
git rev-list --left-right --count origin/arena/01a087d1-ctb...HEAD   # 0<TAB>0
```

A `0  0` (left/right) result means the local branch and the remote branch are
identical.

---

## Two-machine workflow (e.g. sandbox + personal PC)

1. Do work on a dedicated branch and **push it** (never push straight to `main`).
2. On the other machine, run the "daily sync" step above to fetch the branch.
3. Open/update a pull request on GitHub for human review (repo policy: no direct
   commits to `main`).
4. After the PR merges to `main`, both machines run step 4 to pull the new
   `main`.

```bash
# on the machine that made the change
git push -u origin arena/01a087d1-ctb

# on every other machine
git fetch --prune origin
git checkout arena/01a087d1-ctb && git pull --ff-only origin arena/01a087d1-ctb
```

---

## 6. AUTO-SYNC — runs 24/7, every hour, survives reboots & power outages

One command sets up a `systemd` service + timer that re-syncs this clone from
GitHub **every hour**, starts automatically after a reboot / power outage, and
catches up any run that was missed while the machine was down
(`Persistent=true`). Run it as root (it installs systemd units):

> **URL gotcha:** the branch name `arena/01a087d1-ctb` contains a slash, and
> `raw.githubusercontent.com` does **not** resolve it (returns **404**) for
> either the plain or `refs/heads/` form. The file is present on the branch —
> it just isn't reachable over `raw`. **Use the GitHub API form below**
> (verified working) instead of `raw`.

```bash
sudo bash <(curl -fsSL "https://api.github.com/repos/cloudshome/CTB/contents/Users/azims/CBT/scripts/install_auto_sync.sh?ref=arena/01a087d1-ctb" | python3 -c "import sys,json,base64;print(base64.b64decode(json.load(sys.stdin)['content']).decode())") \
  --repo https://github.com/cloudshome/CTB.git \
  --target /home/st/SKY/CTB \
  --interval 1h
```

> Requires `python3` (present on most systems). The whole pipeline is one
> command; the script downloads through `api.github.com`, decodes the base64
> body, and immediately runs the installer with the given options.

- `--target` is the **repo root** (e.g. `/home/st/SKY/CTB`); the project then
  lives at `/home/st/SKY/CTB/Users/azims/CBT`.
- `--interval` controls frequency (default `1h`, i.e. every hour).
- `--branch` is the branch kept checked out (default `main`).

What it installs:

| Component | Purpose |
|---|---|
| `ctb-sync.service` | one-shot: runs the sync script (`/home/st/SKY/CTB/ctb-sync.sh`) |
| `ctb-sync.timer` | triggers the service every `--interval`, `Persistent=true`, enabled at boot |
| `ctb-sync.log`   | append log of every run |

Useful commands:

```bash
systemctl status ctb-sync.timer        # is it active/armed?
systemctl list-timers ctb-sync.timer   # when is the next run?
systemctl start ctb-sync.service       # run once immediately (manual)
journalctl -u ctb-sync.service         # or tail -f /home/st/SKY/CTB/ctb-sync.log
```

The installer writes its **own self-contained** `ctb-sync.sh` into the repo
root, so auto-sync works even if the current GitHub `main` has not yet got the
script. If the machine has no systemd, it installs an equivalent `/etc/cron.d/`
job instead.

> Note: timing depends on the machine being powered on. `Persistent=true`
> means the *first* thing it does after boot is run whatever sync was missed
> while the machine was off — no manual catch-up needed.

---

## Notes

- The sync is **pull-only** (fast-forward). It never pushes and never opens PRs.
- `sync_local.sh` (one-shot, manual) and `ctb-sync.sh` (written by the
  installer, used by the timer) are equivalent; use whichever is present.
- It treats GitHub as authoritative. Any un-pushed local edit is not "the
  repo" and can be lost on the next sync.
- `main` still requires a PR + human review before anything lands there.

Manual convenience script (same commands as `sync_local.sh`, one shot):
`scripts/sync_local.sh`.
