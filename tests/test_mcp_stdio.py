"""Tests for the ZERO-DEPENDENCY root MCP server (mcp_server.py).

`python main.py mcp` runs the SDK-based server (ai/mcp_server.py); the root
`mcp_server.py` is the dependency-free fallback that speaks newline-delimited
JSON-RPC 2.0 over stdio, exposing read-only desk tools (ask / risk / health /
brief / tradestate / postreview) with the permission map enforced.

These tests spawn it as a subprocess exactly like an MCP client would.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server.py"

ROOT_TOOLS = {"ask", "tradestate", "risk", "health", "brief", "postreview"}


class StdioClient:
    def __init__(self, env: dict):
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env, cwd=str(ROOT), bufsize=1)
        self._id = 0

    def send(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line.strip(), f"server died: {self.proc.stderr.read()[-400:]}"
        resp = json.loads(line)
        assert resp.get("id") == self._id
        return resp

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=8)
        except Exception:
            self.proc.kill()
            self.proc.wait()


@pytest.fixture
def env(tmp_path):
    env = dict(os.environ)
    env["DEMO_MODE"] = "1"
    env["DB_PATH"] = str(tmp_path / "root_mcp.db")
    env["PYTHONUNBUFFERED"] = "1"
    env["PROGRESSION"] = "student"
    return env


def test_root_mcp_handshake_and_tools(env):
    client = StdioClient(env)
    try:
        init = client.send("initialize")
        assert init["result"]["serverInfo"]["name"] == "cryptobrain-mcp"
        assert "protocolVersion" in init["result"]

        tools = client.send("tools/list")["result"]["tools"]
        assert {t["name"] for t in tools} == ROOT_TOOLS
        for t in tools:
            assert t["inputSchema"]["type"] == "object"

        risk = client.send("tools/call", {"name": "risk", "arguments": {}})
        payload = json.loads(risk["result"]["content"][0]["text"])
        assert payload["allowed"] is True
        assert payload["open"] is True

        ans = client.send("tools/call", {"name": "ask", "arguments": {
            "query": "what are the daily and weekly loss limits?"}})
        payload = json.loads(ans["result"]["content"][0]["text"])
        assert "risk_rules" in payload["citations"]
        assert "daily" in payload["answer"].lower()
    finally:
        client.close()


def test_root_mcp_permission_map_blocks_unknown_tools(env):
    client = StdioClient(env)
    try:
        client.send("initialize")
        resp = client.send("tools/call", {"name": "place_order", "arguments": {}})
        # read-only map: the tool MUST NOT exist; an explicit error is returned
        assert "error" in resp
        assert "not permitted" in resp["error"]["message"]
    finally:
        client.close()


def test_root_mcp_method_not_found(env):
    client = StdioClient(env)
    try:
        resp = client.send("nonexistent/method")
        assert resp["error"]["code"] == -32601
    finally:
        client.close()


def test_root_mcp_tradestate_roundtrip(env):
    client = StdioClient(env)
    try:
        client.send("initialize")
        resp = client.send("tools/call", {"name": "tradestate", "arguments": {
            "action": "set", "tired": True, "note": "long night"}})
        state = json.loads(resp["result"]["content"][0]["text"])
        assert state["tired"] in (True, 1)

        resp = client.send("tools/call", {"name": "risk", "arguments": {}})
        gate = json.loads(resp["result"]["content"][0]["text"])
        assert gate["allowed"] is False
        assert any("trader state" in b for b in gate["blocked_by"])

        resp = client.send("tools/call", {"name": "tradestate",
                                          "arguments": {"action": "clear"}})
        state = json.loads(resp["result"]["content"][0]["text"])
        assert state["any"] is False
    finally:
        client.close()


def test_root_mcp_health_tool(env):
    client = StdioClient(env)
    try:
        client.send("initialize")
        resp = client.send("tools/call", {"name": "health", "arguments": {}})
        report = json.loads(resp["result"]["content"][0]["text"])
        assert report["status"] in ("OK", "WARN", "CRITICAL")
        assert len(report["checks"]) >= 3
        names = {c["name"] for c in report["checks"]}
        assert {"database_integrity", "risk_system"} <= names
    finally:
        client.close()
