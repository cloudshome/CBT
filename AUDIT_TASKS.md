# CBT/SKY Audit Fix Tasks — Session Plan

## Status Legend
- [ ] Not started
- [x] Done
- [~] In progress

---

## Phase 1: CRITICAL — Unblock .exe Build (Bugs 1–6)

### Task 1: Remove circular dependency in `frontend/package.json`
- **Bug:** #2 — `"ctb-terminal": "file:.."` creates circular dep
- **File:** `frontend/package.json` line 13
- **Action:** Remove the `ctb-terminal` dependency. If shared types needed, use TS path alias.
- [ ] Fix applied
- [ ] `npm install` in frontend passes
- [ ] `npm run build` in frontend passes

### Task 2: Fix `build_windows_app.py` `shell=True` 
- **Bug:** #6 — `subprocess.run(cmd, shell=True)` with list args ignores arguments on Windows
- **File:** `scripts/build_windows_app.py` line 51
- **Action:** Remove `shell=True`
- [ ] Fix applied
- [ ] Gate checks run with correct arguments

### Task 3: Fix Electron dynamic port discovery
- **Bug:** #3 — Electron hardcodes port 8000, backend may start on another port
- **File:** `electron/main.ts` line 19
- **Action:** Parse `CBT_BACKEND_READY:` from backend stdout to get actual port
- [ ] Fix applied

### Task 4: Fix `preload.ts` security — move `shell.openExternal` to IPC
- **Bug:** #5 — Direct `shell.openExternal` in preload bypasses contextIsolation
- **File:** `electron/preload.ts` line 19, `electron/main.ts`
- **Action:** Route through IPC with URL validation
- [ ] Fix applied

### Task 5: Bundle Python backend in electron-builder
- **Bug:** #4 — `electron-builder.json` doesn't include Python backend files
- **File:** `electron-builder.json`
- **Action:** Add `cbt_backend.py`, `app.py`, `core/**/*`, `requirements.txt` to files array
- [ ] Fix applied

### Task 6: Fix Windows SIGTERM in Electron
- **Bug:** #24 — `SIGTERM` is no-op on Windows
- **File:** `electron/main.ts` line 357
- **Action:** Use `backendProcess.kill()` (sends SIGKILL-like) or `taskkill`
- [ ] Fix applied

---

## Phase 2: HIGH — Frontend & Docker Fixes (Bugs 7–10)

### Task 7: Fix useEffect missing deps in App.tsx
- **Bug:** #7 — Stale closure risk
- **File:** `frontend/src/App.tsx` line 394
- [ ] Fix applied

### Task 8: Remove duplicate nginx `/api/kronos` location
- **Bug:** #9
- **File:** `frontend/nginx.conf` line 95
- [ ] Fix applied

### Task 9: Add missing Vite proxy route `/api/health`
- **Bug:** #10 — Dev/prod route parity gap
- **File:** `frontend/vite.config.ts`
- [ ] Fix applied

### Task 10: Fix Docker compose deprecated version field
- **Bug:** #12
- **File:** `docker-compose.yml` line 1
- [ ] Fix applied

---

## Phase 3: MEDIUM — Build Pipeline & Quality (Bugs 15–19)

### Task 11: Fix G-21 human gate auto-pass
- **Bug:** #15 — Always `True`, no actual gate
- **File:** `scripts/build_windows_app.py` line 427
- [ ] Fix applied

### Task 12: Fix G-16 swallowed checksum error
- **Bug:** #16
- **File:** `scripts/build_windows_app.py` line 476-481
- [ ] Fix applied

### Task 13: Generate proper Windows ICO file
- **Bug:** #17 — favicon.ico is web-only resolution
- [ ] Fix applied

---

## Phase 4: LOW — Polish (Bugs 20–24)

### Task 14: Replace Math.random() toast IDs with crypto.randomUUID()
- **File:** `frontend/src/App.tsx` line 146
- [ ] Fix applied

### Task 15: Fix CSS WebkitAppRegion → app-region
- **File:** `frontend/src/App.tsx` line 455
- [ ] Fix applied

---

## Commit Plan
1. `fix(frontend): remove circular ctb-terminal dependency`
2. `fix(build): remove shell=True from subprocess calls in build script`
3. `fix(electron): add dynamic backend port discovery via stdout parsing`
4. `fix(electron): move shell.openExternal to IPC for security`
5. `fix(build): bundle Python backend files in electron-builder config`
6. `fix(electron): use process.kill() instead of SIGTERM on Windows`
7. `fix(frontend): add missing useEffect dependencies in App.tsx`
8. `fix(nginx): remove duplicate /api/kronos location block`
9. `fix(frontend): add /api/health to Vite proxy for dev parity`
10. `chore(docker): remove deprecated version field from compose`
11. `fix(build): implement actual human gate check in release pipeline`
12. `fix(build): surface checksum generation errors`
13. `fix(frontend): use crypto.randomUUID for toast IDs + CSS app-region`
