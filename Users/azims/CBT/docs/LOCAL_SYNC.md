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

## What this repo does NOT do

- It does **not** auto-push or auto-pull. Sync is manual (or via CI on GitHub).
- It treats GitHub as authoritative. Any manual edit in a local clone (that is
  not pushed) is not "the repo" and can be lost.
- It deliberately requires a PR + human review before anything reaches `main`.

A convenience script (same commands, one shot) lives at
`scripts/sync_local.sh`.
