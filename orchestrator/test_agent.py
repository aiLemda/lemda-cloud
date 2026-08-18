import asyncio
import json
from typing import Any

import pytest

import agent
from agent import MAX_HISTORY_TURNS, MAX_STEPS, run_agent


def _ok_result() -> dict[str, Any]:
    return {
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
        "timed_out": False,
        "duration_ms": 1,
    }


@pytest.fixture(autouse=True)
def fake_session(monkeypatch) -> dict[str, list[str]]:
    """Every run opens one sandbox session; patch it so tests never touch Docker."""
    log: dict[str, list[str]] = {"created": [], "closed": []}

    async def create(image=None) -> str:
        sid = f"sess-{len(log['created'])}"
        log["created"].append(sid)
        return sid

    async def close(session_id: str) -> None:
        log["closed"].append(session_id)

    monkeypatch.setattr("sandbox.sandbox_create_session", create)
    monkeypatch.setattr("sandbox.sandbox_close_session", close)
    return log


def _tool_msg(cmd: str, call_id: str = "call_1") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "run_bash", "arguments": json.dumps({"cmd": cmd})},
            }
        ],
    }


def test_answers_without_tools(monkeypatch) -> None:
    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        return {
            "role": "assistant",
            "content": "<answer>42</answer>",
            "tool_calls": None,
        }

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    result = run_agent_sync("what is 2+2?")
    assert result["ok"] is True
    assert result["answer"] == "42"
    assert result["steps"] == []


def test_uses_bash_tool(monkeypatch) -> None:
    calls = {"n": 0}

    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_msg("ls -la /")
        return {
            "role": "assistant",
            "content": "<answer>files listed</answer>",
            "tool_calls": None,
        }

    async def fake_exec(cmd, session_id=None, image=None, timeout_s=30) -> dict:
        assert cmd == "ls -la /"
        return {
            "exit_code": 0,
            "stdout": "bin\nlib\n",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 1,
        }

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    monkeypatch.setattr("sandbox.sandbox_exec", fake_exec)
    result = run_agent_sync("list files")
    assert result["ok"] is True
    assert result["answer"] == "files listed"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["cmd"] == "ls -la /"


def test_tag_fallback_when_no_tool_calling(monkeypatch) -> None:
    calls = {"n": 0}

    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": "<bash>echo hi</bash>",
                "tool_calls": None,
            }
        return {
            "role": "assistant",
            "content": "<answer>hi back</answer>",
            "tool_calls": None,
        }

    async def fake_exec(cmd, session_id=None, image=None, timeout_s=30) -> dict:
        return {
            "exit_code": 0,
            "stdout": "hi\n",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 1,
        }

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    monkeypatch.setattr("sandbox.sandbox_exec", fake_exec)
    result = run_agent_sync("say hi")
    assert result["ok"] is True
    assert result["answer"] == "hi back"
    assert result["steps"][0]["cmd"] == "echo hi"


def test_max_steps_guard(monkeypatch) -> None:
    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        return _tool_msg("echo looping", call_id="call_loop")

    async def fake_exec(cmd, session_id=None, image=None, timeout_s=30) -> dict:
        return {
            "exit_code": 0,
            "stdout": "still here",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 1,
        }

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    monkeypatch.setattr("sandbox.sandbox_exec", fake_exec)
    result = run_agent_sync("loop forever")
    assert result["ok"] is False
    assert "max steps" in result["error"]
    assert len(result["steps"]) == MAX_STEPS


def test_on_step_fires_per_tool_step(monkeypatch) -> None:
    calls = {"n": 0}

    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        calls["n"] += 1
        if calls["n"] <= 2:
            return _tool_msg(f"echo run {calls['n']}", call_id=f"call_{calls['n']}")
        return {
            "role": "assistant",
            "content": "<answer>all done</answer>",
            "tool_calls": None,
        }

    async def fake_exec(cmd, session_id=None, image=None, timeout_s=30) -> dict:
        return {
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 1,
        }

    streamed: list[dict[str, Any]] = []
    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    monkeypatch.setattr("sandbox.sandbox_exec", fake_exec)
    result = asyncio.run(run_agent("run twice", on_step=streamed.append))
    assert result["ok"] is True
    assert len(streamed) == 2
    assert streamed[0]["cmd"] == "echo run 1"
    assert streamed[1]["cmd"] == "echo run 2"
    assert streamed[0]["result"]["exit_code"] == 0


def test_session_lifecycle_reused_and_closed(monkeypatch, fake_session) -> None:
    calls = {"n": 0}
    exec_sessions: list[str] = []

    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_msg("echo a")
        return {
            "role": "assistant",
            "content": "<answer>done</answer>",
            "tool_calls": None,
        }

    async def fake_exec(cmd, session_id=None, image=None, timeout_s=30) -> dict:
        exec_sessions.append(session_id)
        return _ok_result()

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    monkeypatch.setattr("sandbox.sandbox_exec", fake_exec)
    result = run_agent_sync("one step")
    assert result["ok"] is True
    assert fake_session["created"] == ["sess-0"]
    assert fake_session["closed"] == ["sess-0"]
    assert exec_sessions == ["sess-0"]


def test_session_closed_even_on_max_steps(monkeypatch, fake_session) -> None:
    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        return _tool_msg("echo looping", call_id="call_loop")

    async def fake_exec(cmd, session_id=None, image=None, timeout_s=30) -> dict:
        return _ok_result()

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    monkeypatch.setattr("sandbox.sandbox_exec", fake_exec)
    result = run_agent_sync("loop forever")
    assert result["ok"] is False
    assert fake_session["created"] == ["sess-0"]
    assert fake_session["closed"] == ["sess-0"]


def test_history_prepended_in_order(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        captured.extend(messages)
        return {
            "role": "assistant",
            "content": "<answer>8</answer>",
            "tool_calls": None,
        }

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    history = [
        {"role": "user", "content": "what is 2+2?"},
        {"role": "assistant", "content": "4"},
        {"role": "user", "content": "and 4+4?"},
    ]
    result = run_agent_sync("and 8+8?", history=history)
    assert result["ok"] is True
    assert result["answer"] == "8"
    assert [m["role"] for m in captured] == [
        "system",
        "user",
        "assistant",
        "user",
        "user",
    ]
    assert captured[-1]["content"] == "and 8+8?"
    assert captured[1]["content"] == "what is 2+2?"


def test_history_filters_garbage(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        captured.extend(messages)
        return {
            "role": "assistant",
            "content": "<answer>ok</answer>",
            "tool_calls": None,
        }

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    history = [
        {"role": "system", "content": "ignored"},
        {"role": "tool", "content": "ignored"},
        {"role": "user", "content": "  "},
        {"role": "user", "content": "real question"},
    ]
    result = run_agent_sync("hi", history=history)
    assert result["ok"] is True
    roles = [m["role"] for m in captured]
    assert roles.count("user") == 2
    assert captured[1]["content"] == "real question"


def test_history_capped_at_max_turns(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        captured.extend(messages)
        return {
            "role": "assistant",
            "content": "<answer>ok</answer>",
            "tool_calls": None,
        }

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    history = [
        {"role": "user", "content": f"turn {i}"} for i in range(MAX_HISTORY_TURNS + 10)
    ]
    result = run_agent_sync("hi", history=history)
    assert result["ok"] is True
    history_count = sum(1 for m in captured if m["role"] == "user") - 1
    assert history_count == MAX_HISTORY_TURNS


def test_answer_tag_filter_strips_split_tags() -> None:
    received: list[str] = []
    f = agent._AnswerTagFilter(received.append)
    for delta in ("<answ", "er>hel", "lo</", "answer>", " world"):
        f.push(delta)
    assert "".join(received) == "hello world"


def test_answer_tag_filter_flushes_held_non_tags() -> None:
    received: list[str] = []
    f = agent._AnswerTagFilter(received.append)
    f.push("x < y")
    f.push(" text")
    f.push(" more")
    f.push("!!!")
    assert "".join(received) == "x < y text more!!!"


def test_run_agent_streams_answer_tokens(monkeypatch) -> None:
    calls = {"n": 0}

    async def fake_chat(messages, tools=None, timeout_s=120, on_token=None) -> dict:
        calls["n"] += 1
        if on_token:
            on_token("<answer>hello ")
            on_token("world</answer>")
        return {
            "role": "assistant",
            "content": "<answer>hello world</answer>",
            "tool_calls": None,
        }

    monkeypatch.setattr("agent.llm.achat_stream", fake_chat)
    tokens: list[str] = []
    result = run_agent_sync("say hello", on_answer_token=tokens.append)
    assert result["ok"] is True
    assert result["answer"] == "hello world"
    assert "".join(tokens) == "hello world"


def run_agent_sync(
    task: str,
    history: list[dict[str, Any]] | None = None,
    on_answer_token=None,
) -> dict[str, Any]:
    return asyncio.run(
        run_agent(task, history=history, on_answer_token=on_answer_token)
    )
