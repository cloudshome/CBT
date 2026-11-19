# PLAN — R7: Strict Python Type Checking Configuration & Verification
**Authority:** Senior Quantitative Systems Architect  
**Role:** Lead Quantitative Systems Engineer  
**Change Class:** Class C  

---

## 1. Architecture & Design
1. **Configuration:**
   - Extend `pyproject.toml` with `[tool.mypy]` and `[tool.pyright]` sections targeting `core.risk.*`, `core.execution.*`, and new core reliability modules.
2. **Automated Verification:**
   - Create `tests/test_strict_type_annotations.py`:
     - Uses `inspect.signature` and `typing.get_type_hints()` to statically audit all functions, dataclasses, and class methods in `core.risk` and core reliability modules.
     - Enforces presence of return annotations on every non-special method.
     - Enforces presence of parameter annotations on every parameter except `self` and `cls`.
     - Validates that `REAL_CAPITAL_ENABLED` is typed as `Final[bool]`.
     - Asserts zero untyped definitions in the critical surface area.
3. **Execution:**
   - Verify all tests pass via pytest.
   - Run Ruff to verify clean lint.
   - Verify zero M18 certified files modified.
