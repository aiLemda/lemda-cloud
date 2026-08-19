import threading
import time
from typing import Any
from uuid import uuid4

MAX_MESSAGES = 50


class ConversationStore:
    """In-memory conversation store.

    Conversations keep the full user/assistant message history server-side,
    so the chat survives page reloads (the UI persists the id in
    localStorage and restores from here). Kept in memory on purpose - a
    restart starts fresh, mirroring the sandbox session model. Idle
    conversations (no writes for `ttl_secs`) are evicted by the reaper.
    """

    def __init__(self, ttl_secs: float, reap_interval_secs: float) -> None:
        self._lock = threading.Lock()
        self._conversations: dict[str, dict[str, Any]] = {}
        self._ttl_secs = ttl_secs
        self._reap_interval_secs = reap_interval_secs

    @property
    def reap_interval(self) -> float:
        return self._reap_interval_secs

    def reap_expired(self) -> int:
        """Evict conversations idle longer than the TTL; returns how many."""
        cutoff = time.time() - self._ttl_secs
        with self._lock:
            expired = [
                cid
                for cid, c in self._conversations.items()
                if c["updated_at"] < cutoff
            ]
            for cid in expired:
                del self._conversations[cid]
        return len(expired)

    def create(self) -> dict[str, Any]:
        cid = f"conv_{uuid4().hex[:12]}"
        now = time.time()
        with self._lock:
            self._conversations[cid] = {
                "id": cid,
                "messages": [],
                "created_at": now,
                "updated_at": now,
            }
        return {"id": cid, "messages": []}

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            convs = sorted(
                self._conversations.values(),
                key=lambda c: c["updated_at"],
                reverse=True,
            )
        return [
            {
                "id": c["id"],
                "message_count": len(c["messages"]),
                "updated_at": c["updated_at"],
                "preview": next(
                    (m["content"] for m in c["messages"] if m["role"] == "user"), ""
                ),
            }
            for c in convs
        ]

    def get(self, cid: str) -> dict[str, Any] | None:
        with self._lock:
            conv = self._conversations.get(cid)
            if conv is None:
                return None
            return {"id": conv["id"], "messages": list(conv["messages"])}

    def append(self, cid: str, role: str, content: str) -> dict[str, Any] | None:
        with self._lock:
            conv = self._conversations.get(cid)
            if conv is None:
                return None
            if content.strip():
                conv["messages"].append({"role": role, "content": content})
                if len(conv["messages"]) > MAX_MESSAGES:
                    del conv["messages"][: len(conv["messages"]) - MAX_MESSAGES]
            conv["updated_at"] = time.time()
            return {"id": conv["id"], "messages": list(conv["messages"])}
