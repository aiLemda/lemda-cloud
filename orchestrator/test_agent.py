import asyncio
import json
from typing import Any

from agent import MAX_STEPS, run_agent


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
    def fake_chat(messages, tools=None, timeout_s=120) -> dict:
        return {
            "role": "assistant",
            "content": "<answer>42</answer>",
            "tool_calls": None,
        }

    monkeypatch.setattr("llm.chat", fake_chat)
    result = run_agent_sync("what is 2+2?")
    assert result["ok"] is True
    assert result["answer"] == "42"
    assert result["steps"] == []


def test_uses_bash_tool(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_chat(messages, tools=None, timeout_s=120) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_msg("ls -la /")
        return {
            "role": "assistant",
            "content": "<answer>files listed</answer>",
            "tool_calls": None,
        }

    async def fake_exec(cmd, image=None, timeout_s=30) -> dict:
        assert cmd == "ls -la /"
        return {
            "exit_code": 0,
            "stdout": "bin\nlib\n",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 1,
        }

    monkeypatch.setattr("llm.chat", fake_chat)
    monkeypatch.setattr("sandbox.sandbox_exec", fake_exec)
    result = run_agent_sync("list files")
    assert result["ok"] is True
    assert result["answer"] == "files listed"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["cmd"] == "ls -la /"


def test_tag_fallback_when_no_tool_calling(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_chat(messages, tools=None, timeout_s=120) -> dict:
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

    async def fake_exec(cmd, image=None, timeout_s=30) -> dict:
        return {
            "exit_code": 0,
            "stdout": "hi\n",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 1,
        }

    monkeypatch.setattr("llm.chat", fake_chat)
    monkeypatch.setattr("sandbox.sandbox_exec", fake_exec)
    result = run_agent_sync("say hi")
    assert result["ok"] is True
    assert result["answer"] == "hi back"
    assert result["steps"][0]["cmd"] == "echo hi"


def test_max_steps_guard(monkeypatch) -> None:
    def fake_chat(messages, tools=None, timeout_s=120) -> dict:
        return _tool_msg("echo looping", call_id="call_loop")

    async def fake_exec(cmd, image=None, timeout_s=30) -> dict:
        return {
            "exit_code": 0,
            "stdout": "still here",
            "stderr": "",
            "timed_out": False,
            "duration_ms": 1,
        }

    monkeypatch.setattr("llm.chat", fake_chat)
    monkeypatch.setattr("sandbox.sandbox_exec", fake_exec)
    result = run_agent_sync("loop forever")
    assert result["ok"] is False
    assert "max steps" in result["error"]
    assert len(result["steps"]) == MAX_STEPS


def run_agent_sync(task: str) -> dict[str, Any]:
    return asyncio.run(run_agent(task))
