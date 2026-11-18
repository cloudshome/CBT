"""
Automated Type Checking and Annotation Completeness Verification Suite.
Verifies:
- Complete parameter and return type annotations across all core/risk/ and core reliability modules.
- Strict typing of constitutional constants (REAL_CAPITAL_ENABLED is Final[bool]).
- Presence and validity of [tool.mypy] and [tool.pyright] configurations in pyproject.toml.
- Zero unannotated public functions or methods in the audited critical surface area.
"""

from __future__ import annotations

import importlib
import inspect
import tomllib
from dataclasses import is_dataclass
from enum import Enum
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_real_capital_enabled_is_strictly_typed_and_false() -> None:
    """Verifies that REAL_CAPITAL_ENABLED is permanently False and strictly annotated."""
    import core.risk.execution_isolation as ei

    assert ei.REAL_CAPITAL_ENABLED is False

    annotations = getattr(ei, "__annotations__", {})
    assert "REAL_CAPITAL_ENABLED" in annotations
    ann = annotations["REAL_CAPITAL_ENABLED"]
    # Should be Final[bool] or contain 'Final'
    assert "Final" in str(ann) and "bool" in str(ann)


def test_pyproject_toml_contains_strict_type_checking_configuration() -> None:
    """Verifies that pyproject.toml defines strict mypy and pyright configurations."""
    pyproject_path = ROOT_DIR / "pyproject.toml"
    assert pyproject_path.exists()

    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)

    tools = config.get("tool", {})
    assert "mypy" in tools
    assert "pyright" in tools

    mypy_cfg = tools["mypy"]
    assert mypy_cfg.get("check_untyped_defs") is True

    overrides = mypy_cfg.get("overrides", [])
    assert len(overrides) >= 1
    strict_override = overrides[0]
    modules = strict_override.get("module", [])

    assert "core.risk.*" in modules
    assert "core.execution.*" in modules
    assert strict_override.get("disallow_untyped_defs") is True
    assert strict_override.get("strict_equality") is True


AUDITED_MODULES = [
    "core.risk.execution_isolation",
    "core.risk.order_authorization",
    "core.risk.asset_eligibility_gate",
    "core.risk.m57_live_gate",
    "core.risk.guardian_supervisor",
    "core.risk.immutable_risk_accounting",
    "core.risk.portfolio_risk_guardian",
    "core.correlation_context",
    "core.database_migrations",
    "core.database_recovery",
    "core.slo_monitor",
    "core.streaming_backpressure",
]


@pytest.mark.parametrize("module_name", AUDITED_MODULES)
def test_audited_modules_have_complete_type_annotations(module_name: str) -> None:
    """
    Verifies that all public functions and class methods in audited modules
    have complete parameter and return type annotations.
    """
    mod = importlib.import_module(module_name)

    # 1. Inspect top-level public functions
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith("_"):
            continue
        if obj.__module__ != module_name:
            continue

        sig = inspect.signature(obj)
        # Check return type annotation
        assert sig.return_annotation is not inspect.Signature.empty, (
            f"Function {module_name}.{name}() is missing return type annotation"
        )

        # Check parameter annotations
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            assert param.annotation is not inspect.Signature.empty, (
                f"Parameter '{param_name}' of {module_name}.{name}() is missing type annotation"
            )

    # 2. Inspect public classes and their public methods
    for cls_name, cls_obj in inspect.getmembers(mod, inspect.isclass):
        if cls_name.startswith("_") or cls_obj.__module__ != module_name:
            continue

        # Skip inspecting Enum base methods
        is_enum = issubclass(cls_obj, Enum)

        for meth_name, meth_obj in inspect.getmembers(cls_obj, inspect.isfunction):
            # Only inspect methods declared directly in this class
            if not meth_obj.__qualname__.startswith(f"{cls_name}."):
                continue
            if meth_name.startswith("_") and not meth_name.startswith("__init__"):
                continue
            # Skip synthesized __init__ on Enum, Exception, or dataclass
            if meth_name == "__init__" and (
                is_enum or issubclass(cls_obj, Exception) or is_dataclass(cls_obj)
            ):
                continue

            sig = inspect.signature(meth_obj)
            # Check return type annotation (except __init__ where None is optional)
            if meth_name != "__init__":
                assert sig.return_annotation is not inspect.Signature.empty, (
                    f"Method {cls_name}.{meth_name}() in {module_name} is missing return type annotation"
                )

            # Check parameter annotations
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue
                assert param.annotation is not inspect.Signature.empty, (
                    f"Parameter '{param_name}' of {cls_name}.{meth_name}() in {module_name} is missing type annotation"
                )
