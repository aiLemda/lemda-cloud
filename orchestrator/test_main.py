import httpx
import pytest
from fastapi.testclient import TestClient

from main import app


def test_health() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "orchestrator"}


def test_sandbox_ls_wiring(monkeypatch) -> None:
    async def fake_exec(cmd, image=None, timeout_s=30) -> dict:
        return {
            "exit_code": 0,
            "stdout": "bin\nlib\n",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 42,
        }

    monkeypatch.setattr("main.sandbox_exec", fake_exec)
    client = TestClient(app)
    resp = client.get("/sandbox/ls")
    assert resp.status_code == 200
    assert "bin" in resp.json()["stdout"]


def test_sandbox_exec_gateway_down(monkeypatch) -> None:
    async def raise_error(cmd, image=None, timeout_s=30) -> dict:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("main.sandbox_exec", raise_error)
    client = TestClient(app)
    resp = client.post("/sandbox/exec", json={"cmd": "echo hi"})
    assert resp.status_code == 502
    assert "gateway call failed" in resp.json()["detail"]
