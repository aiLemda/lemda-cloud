from fastapi.testclient import TestClient

from main import app


def test_agent_run_wiring(monkeypatch) -> None:
    async def fake_run(
        task: str, max_steps: int = 10, on_step=None, history=None
    ) -> dict:
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
    async def fake_run(
        task: str, max_steps: int = 10, on_step=None, history=None, on_answer_token=None
    ) -> dict:
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


def test_agent_run_stream_emits_answer_tokens(monkeypatch) -> None:
    async def fake_run(
        task: str, max_steps: int = 10, on_step=None, history=None, on_answer_token=None
    ) -> dict:
        if on_answer_token:
            on_answer_token("<answer>hel")
            on_answer_token("lo</answer>")
        return {"ok": True, "answer": "hello", "steps": []}

    monkeypatch.setattr("main.run_agent", fake_run)
    client = TestClient(app)
    with client.stream("POST", "/agent/run/stream", json={"task": "hi"}) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert body.count("event: answer_token") == 2
    assert '"delta": "lo</answer>"' in body
    assert "event: result" in body


def test_agent_run_forwards_history(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_run(
        task: str, max_steps: int = 10, on_step=None, history=None
    ) -> dict:
        seen.update({"task": task, "history": history})
        return {"ok": True, "answer": "done", "steps": []}

    monkeypatch.setattr("main.run_agent", fake_run)
    client = TestClient(app)
    history = [
        {"role": "user", "content": "what is 2+2?"},
        {"role": "assistant", "content": "4"},
    ]
    resp = client.post("/agent/run", json={"task": "and 4+4?", "history": history})
    assert resp.status_code == 200
    assert seen["task"] == "and 4+4?"
    assert seen["history"] == history
