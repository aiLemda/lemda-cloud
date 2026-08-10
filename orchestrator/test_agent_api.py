from fastapi.testclient import TestClient

from main import app


def test_agent_run_wiring(monkeypatch) -> None:
    async def fake_run(task: str, max_steps: int = 10) -> dict:
        return {
            "ok": True,
            "answer": "files listed",
            "steps": [{"type": "tool", "cmd": "ls -la /", "result": {}}],
        }

    monkeypatch.setattr("main.run_agent", fake_run)
    client = TestClient(app)
    resp = client.post("/agent/run", json={"task": "list files"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["answer"] == "files listed"
    assert len(body["steps"]) == 1
    assert body["steps"][0]["cmd"] == "ls -la /"


def test_agent_run_rejects_empty_task() -> None:
    client = TestClient(app)
    resp = client.post("/agent/run", json={"task": "   "})
    assert resp.status_code == 422
    assert "task must not be empty" in resp.json()["detail"]
