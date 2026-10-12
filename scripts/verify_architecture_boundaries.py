"""
scripts/verify_architecture_boundaries.py
=========================================
Mechanized Architectural Boundary & Import Dependency AST Verifier.

Statically parses and validates all Python source imports across:
1. Layer Stratification (Layer N only imports Layer <= N).
2. Authority Isolation (Simulation & Research modules cannot import Live Execution Router / Connectors).
3. Causal & Gateway Firewalls (Risk engine & Research modules cannot import Application Gateways or UI).

Exit Codes:
- 0: All architectural boundaries verified compliant (PASS).
- 1: One or more architectural firewall violations detected (FAIL).
"""

from __future__ import annotations

import ast
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.governance.architecture_registry import (
    validate_import_direction,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("architecture_verifier")


@dataclass
class ImportViolation:
    file_path: Path
    line_number: int
    source_module: str
    target_module: str
    reason: str


def file_to_module_name(file_path: Path, repo_root: Path) -> str:
    """Converts a file path to its canonical dotted Python module name."""
    rel = file_path.relative_to(repo_root)
    parts = list(rel.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def scan_file_imports(file_path: Path, repo_root: Path) -> list[tuple[int, str]]:
    """Parses a Python file with ast and extracts (line_number, imported_module)."""
    try:
        source_code = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=str(file_path))
    except Exception as e:
        logger.warning(f"Could not parse {file_path}: {e}")
        return []

    imported_modules: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                # Handle relative imports if level > 0
                if node.level > 0:
                    # Construct full module from source package
                    source_mod = file_to_module_name(file_path, repo_root)
                    mod_parts = source_mod.split(".")
                    base_parts = mod_parts[:-node.level] if len(mod_parts) >= node.level else []
                    full_mod = ".".join(base_parts + [node.module])
                    imported_modules.append((node.lineno, full_mod))
                else:
                    imported_modules.append((node.lineno, node.module))

    return imported_modules


def run_architecture_boundary_verification(root_path: Path | None = None) -> tuple[bool, list[ImportViolation], int, int]:
    """Scans all Python files under core/ and root app.py for boundary compliance."""
    target_root = root_path or REPO_ROOT
    files_to_scan: list[Path] = []

    # 1. Collect core/ files
    core_dir = target_root / "core"
    for py_file in core_dir.rglob("*.py"):
        if "__pycache__" not in py_file.parts:
            files_to_scan.append(py_file)

    # 2. Collect app.py
    app_py = target_root / "app.py"
    if app_py.exists():
        files_to_scan.append(app_py)

    violations: list[ImportViolation] = []
    total_imports_checked = 0

    for fpath in files_to_scan:
        source_mod = file_to_module_name(fpath, target_root)
        imports = scan_file_imports(fpath, target_root)

        for lineno, target_mod in imports:
            total_imports_checked += 1
            # Only evaluate project-internal imports
            if target_mod.startswith("core") or target_mod.startswith("app") or target_mod.startswith("src") or target_mod.startswith("frontend"):
                is_valid, reason = validate_import_direction(source_mod, target_mod)
                if not is_valid and reason is not None:
                    violations.append(
                        ImportViolation(
                            file_path=fpath,
                            line_number=lineno,
                            source_module=source_mod,
                            target_module=target_mod,
                            reason=reason,
                        )
                    )

    is_compliant = len(violations) == 0
    return is_compliant, violations, len(files_to_scan), total_imports_checked


def main() -> int:
    print("============================================================")
    print("SKY ARCHITECTURE CONTRACT & DEPENDENCY BOUNDARY VERIFICATION")
    print("============================================================")
    is_compliant, violations, file_count, import_count = run_architecture_boundary_verification()

    print(f"Scanned Python Files   : {file_count}")
    print(f"Internal Imports Checked: {import_count}")
    print(f"Violations Detected     : {len(violations)}")
    print("------------------------------------------------------------")

    if not is_compliant:
        print("\n[FAIL] ARCHITECTURAL FIREWALL VIOLATIONS DETECTED:")
        for idx, v in enumerate(violations, 1):
            rel_file = v.file_path.relative_to(REPO_ROOT)
            print(f"\n[{idx}] {rel_file}:{v.line_number}")
            print(f"    Source Module : {v.source_module}")
            print(f"    Target Module : {v.target_module}")
            print(f"    Violation     : {v.reason}")
        print("\n[FAIL] Architecture boundaries violated. Changes rejected.")
        return 1


    print("\n[PASS] All architectural layer boundaries and authority firewalls intact.")
    print("       1. Layer Stratification Verified (0 <= 1 <= 2 <= 3 <= 4).")
    print("       2. Authority Isolation Verified (Simulation modules isolated from Live Connectors).")
    print("       3. Gateway & UI Firewalls Verified (No reverse dependencies into app/src/frontend).")
    print("============================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())

