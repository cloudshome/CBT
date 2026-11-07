# SKY / CBT — Python 3.13 Verification Environment Specification & Reproducibility Guide

## 1. Overview & CI Alignment

Milestone 18 certification gates, C-extensions, and quantitative backtesting in SKY / CBT depend on binary CPython ABI compatibility.

- **Authoritative CI Specification:** [`.github/workflows/ci.yml`](file:///home/cloudslover/CBT/.github/workflows/ci.yml#L46) explicitly designates **Python 3.13**:
  ```yaml
  - name: Set up Python
    uses: actions/setup-python@v5
    with:
      python-version: '3.13'
  ```
- **Target Subsystems Dependent on ABI:**
  - `pydantic_core._pydantic_core`: Fast JSON & data validation backend (compiled C-extension).
  - `cryptography` / `_cffi_backend`: AES-256-GCM authenticated vault backup encryption and JWT verification.
  - `numpy`: Numerical calculations and statistical trade reconciliation.

---

## 2. Problem Diagnosis: The Host Python 3.14 ABI Mismatch

On modern Linux environments where `/usr/bin/python3` has rolled forward to **Python 3.14 (pre-release)**:
- Pre-compiled virtual environments (`.venv/lib/python3.13/site-packages`) containing `.cpython-313-x86_64-linux-gnu.so` files cannot be loaded by Python 3.14.
- Attempting to run Pytest with Python 3.14 against Python 3.13 site-packages triggers:
  ```text
  ImportError: cannot import name 'ArgsKwargs' from 'pydantic_core._pydantic_core'
  ```
- This is strictly an **environment ABI mismatch**, not an application defect or certified code failure.

---

## 3. Dedicated Verification Environment (`.venv-m18-verify`)

To ensure deterministic, reproducible verification without mutating the existing `.venv` or modifying application code:

1. **Interpreter Path:** CPython 3.13.15 is provisioned locally in `.python313/bin/python3` (or discovered via `uv` at `~/.local/share/uv/python/cpython-3.13*/bin/python3`).
2. **Virtualenv Location:** `.venv-m18-verify`
3. **Automated Setup Script:**
   ```bash
   python3 scripts/setup_verification_env.py
   ```
4. **Environment Health Check:**
   ```bash
   .venv-m18-verify/bin/python -c "from pydantic_core._pydantic_core import ArgsKwargs; import cryptography; print('ABI OK')"
   ```

---

## 4. Running the 14 Milestone 18 Certification Gates

With `.venv-m18-verify` active, execute the cryptographic verification script:

```bash
.venv-m18-verify/bin/python scripts/verify_m18_certification.py
```

### Verification Verification Checklist:
- [x] Invariant 9: Certified commit `c9cc1cad` is confirmed as an ancestor of `HEAD`.
- [x] Invariant 2: All 14 certified execution files exist on disk.
- [x] Invariant 10: Cryptographic test identity hash matches `2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b`.
- [x] All 149 adversarial tests execute and pass (149 passed, 0 failed, 0 skipped).
- [x] Exit code: 0.

---

## 5. Summary of Dependencies

| Package | Version | ABI Tag | Purpose |
|:---|:---:|:---:|:---|
| `python` | 3.13.15 | `cpython-313` | Canonical runtime matching CI |
| `pydantic` | 2.10.4 | pure Python | Data models and request contracts |
| `pydantic-core` | 2.27.2 | `cpython-313-x86_64-linux-gnu` | High-performance C model parsing |
| `cryptography` | 44.0.0 | `cpython-313-x86_64-linux-gnu` | AES-256-GCM authenticated vault cipher |
| `pytest` | 8.3.4 / 9.1.1 | pure Python | Adversarial test harness |
| `fastapi` | 0.115.6 | pure Python | Execution REST gateway |
