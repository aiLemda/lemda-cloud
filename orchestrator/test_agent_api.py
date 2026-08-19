from fastapi.testclient import TestClient

import main
from main import app


def _async_lambda(fn):
    async def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


def test_agent_run_wiring(monkeypatch) -> None:
    async def fake_run(
        task: str,
        max_steps: int = 10,
        on_step=None,
        history=None,
        session_id=None,
        on_answer_token=None,
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
        task: str,
        max_steps: int = 10,
        on_step=None,
        history=None,
        on_answer_token=None,
        session_id=None,
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
        task: str,
        max_steps: int = 10,
        on_step=None,
        history=None,
        on_answer_token=None,
        session_id=None,
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


def test_pinned_session_reused_when_alive(monkeypatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        "main.session_alive", _async_lambda(lambda sid: sid == "sess-alive")
    )
    created: list[str] = []

    async def fake_create(image=None) -> str:
        sid = f"sess-{len(created)}"
        created.append(sid)
        return sid

    async def fake_run(
        task,
        max_steps=10,
        on_step=None,
        history=None,
        on_answer_token=None,
        session_id=None,
    ) -> dict:
        seen.update({"task": task, "session_id": session_id})
        return {"ok": True, "answer": "done", "steps": []}

    monkeypatch.setattr("main.sandbox_create_session", fake_create)
    monkeypatch.setattr("main.run_agent", fake_run)
    client = TestClient(app)
    cid = client.post("/conversations").json()["id"]
    main.conversations.set_session(cid, "sess-alive")
    resp = client.post(
        "/agent/run",
        json={"task": "hi", "conversation_id": cid},
    )
    assert resp.status_code == 200
    assert seen["session_id"] == "sess-alive"
    assert created == []


def test_stale_pinned_session_recreated(monkeypatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr("main.session_alive", _async_lambda(lambda sid: False))
    created: list[str] = []

    async def fake_create(image=None) -> str:
        sid = f"sess-{len(created)}"
        created.append(sid)
        return sid

    async def fake_run(
        task,
        max_steps=10,
        on_step=None,
        history=None,
        on_answer_token=None,
        session_id=None,
    ) -> dict:
        seen.update({"task": task, "session_id": session_id})
        return {"ok": True, "answer": "done", "steps": []}

    monkeypatch.setattr("main.sandbox_create_session", fake_create)
    monkeypatch.setattr("main.run_agent", fake_run)
    client = TestClient(app)
    cid = client.post("/conversations").json()["id"]
    main.conversations.set_session(cid, "sess-stale")
    resp = client.post(
        "/agent/run",
        json={"task": "hi", "conversation_id": cid},
    )
    assert resp.status_code == 200
    assert seen["session_id"] == "sess-0"
    assert created == ["sess-0"]
    assert main.conversations.get_session(cid) == "sess-0"


def test_unknown_conversation_runs_unpinned(monkeypatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr("main.session_alive", _async_lambda(lambda sid: True))
    created: list[str] = []

    async def fake_create(image=None) -> str:
        created.append("sess-x")
        return "sess-x"

    async def fake_run(
        task,
        max_steps=10,
        on_step=None,
        history=None,
        on_answer_token=None,
        session_id=None,
    ) -> dict:
        seen.update({"task": task, "session_id": session_id})
        return {"ok": True, "answer": "done", "steps": []}

    monkeypatch.setattr("main.sandbox_create_session", fake_create)
    monkeypatch.setattr("main.run_agent", fake_run)
    client = TestClient(app)
    resp = client.post(
        "/agent/run",
        json={"task": "hi", "conversation_id": "conv_nope"},
    )
    assert resp.status_code == 200
    assert seen["session_id"] is None
    assert created == []


def test_agent_run_forwards_history(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_run(
        task: str,
        max_steps: int = 10,
        on_step=None,
        history=None,
        on_answer_token=None,
        session_id=None,
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
