import json
import re
from collections.abc import Callable
from typing import Any

import llm
import sandbox

MAX_STEPS = 10
MAX_HISTORY_TURNS = 20

SYSTEM_PROMPT = """You are a coding agent running inside a Linux sandbox (root, python:3.12-slim).
You have exactly ONE tool: run_bash - it runs a shell command in the sandbox and returns its output.
Rules:
- Use run_bash to explore and complete the user's task.
- The sandbox network only reaches GitHub, PyPI, and npm. Do not expect other sites.
- Prefer short, safe commands.
- When the task is finished, reply with a final answer inside <answer>...</answer> tags.
- If you need to run a command but tool calling is unavailable, reply with <bash>command</bash> instead.
"""

BASH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_bash",
        "description": "Run a shell command inside the Linux sandbox. Returns stdout, stderr and exit code.",
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "the shell command to run"}
            },
            "required": ["cmd"],
        },
    },
}


def _summarize(result: dict[str, Any]) -> str:
    out = result.get("stdout", "")
    err = result.get("stderr", "")
    if result.get("timed_out"):
        return "command timed out - sandbox container killed"
    if err and not out:
        return f"exit_code={result.get('exit_code')} stderr:\n{err}"
    if out:
        return f"exit_code={result.get('exit_code')} stdout:\n{out}"
    return f"exit_code={result.get('exit_code')} (no output)"


def _sanitize_history(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Keep only well-formed user/assistant turns, oldest first, capped."""
    if not history:
        return []
    cleaned: list[dict[str, Any]] = []
    for turn in history:
        role = turn.get("role")
        content = turn.get("content")
        if (
            role in ("user", "assistant")
            and isinstance(content, str)
            and content.strip()
        ):
            cleaned.append({"role": role, "content": content})
    return cleaned[-MAX_HISTORY_TURNS:]


_ANSWER_TAG_RE = re.compile(r"<answer\s*>|</answer\s*>")
_MAX_TAG_LEN = 15


class _AnswerTagFilter:
    """Streams content through, dropping <answer>...</answer> tag delimiters
    even when they are split across token boundaries.

    A trailing run that could still become a tag is held back until the next
    token decides; anything longer than a tag can possibly be is flushed."""

    def __init__(self, on_delta: Callable[[str], None]) -> None:
        self._on_delta = on_delta
        self._buffer = ""

    def push(self, delta: str) -> None:
        cleaned = _ANSWER_TAG_RE.sub("", self._buffer + delta)
        idx = cleaned.rfind("<")
        if idx != -1 and len(cleaned) - idx <= _MAX_TAG_LEN:
            emit, self._buffer = cleaned[:idx], cleaned[idx:]
        else:
            emit, self._buffer = cleaned, ""
        if emit:
            self._on_delta(emit)


async def run_agent(
    task: str,
    max_steps: int = MAX_STEPS,
    on_step: Callable[[dict[str, Any]], None] | None = None,
    history: list[dict[str, Any]] | None = None,
    on_answer_token: Callable[[str], None] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Run the agent loop inside one persistent sandbox session.

    The session container is created once, every command runs inside it, and
    it is removed when the run finishes - so files and installs survive
    between steps. `history` carries prior conversation turns so the agent
    can answer follow-ups with full context. `on_answer_token` receives the
    model's answer text as it is generated (answer tags stripped).
    With `session_id` the run reuses a pinned session (a conversation's
    workspace) and never closes it - the conversation reaper owns that.
    """
    if session_id:
        return await _run_agent(
            task, session_id, max_steps, on_step, history, on_answer_token
        )
    session_id = await sandbox.sandbox_create_session()
    try:
        return await _run_agent(
            task, session_id, max_steps, on_step, history, on_answer_token
        )
    finally:
        await sandbox.sandbox_close_session(session_id)


async def _run_agent(
    task: str,
    session_id: str,
    max_steps: int = MAX_STEPS,
    on_step: Callable[[dict[str, Any]], None] | None = None,
    history: list[dict[str, Any]] | None = None,
    on_answer_token: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *_sanitize_history(history),
        {"role": "user", "content": task},
    ]
    steps: list[dict[str, Any]] = []
    tag_filter = _AnswerTagFilter(on_answer_token) if on_answer_token else None

    for _ in range(max_steps):
        try:
            message = await llm.achat_stream(
                messages,
                tools=[BASH_TOOL],
                on_token=tag_filter.push if tag_filter else None,
            )
        except Exception as e:  # noqa: BLE001 - LLM providers throw heterogeneous exceptions; the loop must survive any of them
            return {"ok": False, "error": f"llm call failed: {e}", "steps": steps}
        messages.append(message)

        content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []

        if tool_calls:
            for call in tool_calls:
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                    cmd = str(args.get("cmd", ""))
                except (json.JSONDecodeError, KeyError):
                    cmd = ""
                if not cmd:
                    result = {
                        "exit_code": None,
                        "stdout": "",
                        "stderr": "no cmd argument provided",
                        "timed_out": False,
                    }
                else:
                    result = await sandbox.sandbox_exec(cmd, session_id=session_id)
                steps.append({"type": "tool", "cmd": cmd, "result": result})
                if on_step:
                    on_step({"type": "tool", "cmd": cmd, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": _summarize(result),
                    }
                )
            continue

        bash_matches = re.findall(r"<bash>(.*?)</bash>", content, re.DOTALL)
        if bash_matches:
            cmd = bash_matches[-1].strip()
            result = await sandbox.sandbox_exec(cmd, session_id=session_id)
            steps.append({"type": "tool", "cmd": cmd, "result": result})
            if on_step:
                on_step({"type": "tool", "cmd": cmd, "result": result})
            messages.append(
                {"role": "user", "content": f"command output:\n{_summarize(result)}"}
            )
            continue

        answer_match = re.search(r"<answer>(.*?)</answer>", content, re.DOTALL)
        if answer_match:
            return {"ok": True, "answer": answer_match.group(1).strip(), "steps": steps}
        if content.strip():
            return {"ok": True, "answer": content.strip(), "steps": steps}

    return {
        "ok": False,
        "error": f"max steps ({max_steps}) reached without a final answer",
        "steps": steps,
    }
