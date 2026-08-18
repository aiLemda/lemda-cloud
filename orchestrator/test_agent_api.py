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


def test_agent_run_stream_emits_steps(monkeypatch) -> None:
    async def fake_run(task: str, max_steps: int = 10, on_step=None) -> dict:
        for n in (1, 2):
            if on_step:
                on_step(
                    {
                        "type": "tool",
                        "cmd": f"echo {n}",
                        "result": {
                            "exit_code": 0,
                            "stdout": str(n),
                            "stderr": "",
                            "timed_out": False,
                            "duration_ms": 1,
                        },
                    }
                )
        return {"ok": True, "answer": "done", "steps": []}

    monkeypatch.setattr("main.run_agent", fake_run)
    client = TestClient(app)
    with client.stream("POST", "/agent/run/stream", json={"task": "hi"}) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert body.count("event: step") == 2
    assert '"cmd": "echo 2"' in body
    assert "event: result" in body
    assert '"answer": "done"' in body
