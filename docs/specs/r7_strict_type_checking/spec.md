# SPEC — R7: Strict Python Type Checking Configuration & Verification
**Authority:** Senior Quantitative Systems Architect  
**Role:** Lead Quantitative Systems Engineer  
**Change Class:** Class C (Engineering Quality & Typing)  
**Status:** DRAFT  

---

## 1. Context & Business Rationale
In quantitative finance, untyped function boundaries and dynamic `Any` propagation cause runtime type errors, silent data coercion, and parameter misalignments. By formalizing strict static type checking definitions in `pyproject.toml` and enforcing runtime annotation completeness via automated inspection, we guarantee that all risk controls, order authorization pathways, and reliability engines are strictly typed.

## 2. Requirements & Acceptance Criteria
1. **Tool Configuration (`pyproject.toml`):**
   - Configure `[tool.mypy]` with baseline settings (`python_version = "3.11"`, `check_untyped_defs = true`, `warn_return_any = true`).
   - Configure strict overrides (`[[tool.mypy.overrides]]`) for critical subsystems:
     - `core.risk.*`
     - `core.execution.*`
     - `core.correlation_context`
     - `core.database_migrations`
     - `core.database_recovery`
     - `core.slo_monitor`
     - `core.streaming_backpressure`
   - Enforce: `disallow_untyped_defs = true`, `disallow_any_generics = true`, `disallow_incomplete_defs = true`, `no_implicit_optional = true`, `strict_equality = true`.
2. **Automated Annotation Audit (`tests/test_strict_type_annotations.py`):**
   - Inspect all modules in `core/risk/` and the newly authored reliability engines (`core.database_recovery`, `core.slo_monitor`, etc.).
   - Assert 100% of public functions and class methods possess explicit return type annotations and parameter type annotations.
   - Assert zero unannotated `*args` or `**kwargs` in public API contracts.
3. **Milestone 18 Certification Invariant:**
   - Zero modifications to the 14 M18 certified files. `pyproject.toml` additions must not break existing test runners or linters.
