"""
GitHub Quantitative Code Researcher & Script Parser.
Parses Python AST, Pine Script (.pine), and MetaTrader MQL5 (.mq5) scripts
from cloned repositories in data/github_sandbox/ to extract algorithmic strategy logic.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.github_researcher")


class GitHubResearcher:
    """Clones and extracts strategy DNA from open-source algorithmic repositories."""

    def __init__(self, sandbox_dir: Path | None = None):
        self.sandbox_dir = sandbox_dir or Path(os.getenv("DATA_DIR", "data")) / "github_sandbox"
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)

    def parse_python_strategy(self, code_str: str) -> dict[str, Any]:
        """
        Parses Python strategy code using AST to identify entry conditions and parameter ranges.
        """
        try:
            tree = ast.parse(code_str)
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

            # Extract numeric assignment constants as parameters
            params: dict[str, Any] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and isinstance(
                            node.value, ast.Constant | ast.Num
                        ):
                            val = node.value.value if hasattr(node.value, "value") else node.value.n
                            if isinstance(val, int | float):
                                params[target.id] = val

            return {
                "language": "Python",
                "classes": classes,
                "functions": functions,
                "extracted_parameters": params,
                "has_entry_logic": any(
                    "entry" in f.lower() or "buy" in f.lower() for f in functions
                ),
                "has_risk_logic": any(
                    "risk" in f.lower() or "stop" in f.lower() for f in functions
                ),
            }
        except Exception as e:
            return {"language": "Python", "error": str(e), "extracted_parameters": {}}

    def parse_pine_script(self, pine_code: str) -> dict[str, Any]:
        """
        Parses TradingView Pine Script for inputs, indicator calculations, and strategy.entry calls.
        """
        inputs = re.findall(r"(\w+)\s*=\s*input\.(?:\w+)\s*\(([^)]+)\)", pine_code)
        entries = re.findall(
            r'strategy\.entry\s*\(\s*["\']([^"\']+)["\']\s*,\s*strategy\.(long|short)',
            pine_code,
            re.IGNORECASE,
        )
        ta_calls = re.findall(r"ta\.(\w+)", pine_code)

        return {
            "language": "PineScript",
            "inputs_count": len(inputs),
            "strategy_entries": entries,
            "technical_indicators_used": list(set(ta_calls)),
            "is_valid_strategy": len(entries) > 0,
        }


# Singleton
github_researcher = GitHubResearcher()
