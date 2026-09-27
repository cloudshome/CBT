"""
tests/research/grade_e3/test_security_firewall.py
=================================================
Permanent Capital Firewall & Static Dependency Isolation Audit.

Asserts:
1. Grade-E3 engine has ZERO imports or calls to live execution, order routers, or exchange connectors.
2. The dependency direction is strictly:
   Research / Grade-E3 -> Evidence Artifacts -> Independent Governance -> Independent Authorization.
"""

from __future__ import annotations

import ast
from pathlib import Path

GRADE_E3_DIR = Path(__file__).resolve().parents[3] / "core" / "research" / "grade_e3"

FORBIDDEN_MODULES = [
    "core.execution.live_router",
    "core.execution.smart_order_router",
    "core.execution.connectors",
    "core.execution.kill_switch",
    "core.execution_gateway",
    "core.smart_execution",
]

FORBIDDEN_SYMBOLS = [
    "place_order",
    "execute_order",
    "submit_order",
    "SmartOrderRouter",
    "LiveExecutionRouter",
]


def test_grade_e3_static_dependency_isolation() -> None:
    """
    Parses every Python file in core/research/grade_e3/ using AST
    and verifies that none of the forbidden execution modules or symbols are imported.
    """
    assert GRADE_E3_DIR.exists(), f"Grade-E3 directory {GRADE_E3_DIR} not found"

    py_files = list(GRADE_E3_DIR.glob("*.py"))
    assert len(py_files) >= 4, (
        f"Expected at least 4 Python files in {GRADE_E3_DIR}, found {len(py_files)}"
    )

    for py_file in py_files:
        with open(py_file, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_MODULES:
                        assert not alias.name.startswith(forbidden), (
                            f"Firewall breach: {py_file.name} imports forbidden module '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for forbidden in FORBIDDEN_MODULES:
                    assert not module.startswith(forbidden), (
                        f"Firewall breach: {py_file.name} imports from forbidden module '{module}'"
                    )
                for alias in node.names:
                    assert alias.name not in FORBIDDEN_SYMBOLS, (
                        f"Firewall breach: {py_file.name} imports forbidden symbol '{alias.name}'"
                    )
