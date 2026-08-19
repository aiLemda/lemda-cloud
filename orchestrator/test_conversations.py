from fastapi.testclient import TestClient

from conversations import ConversationStore
from main import app

client = TestClient(app)


def test_create_and_get_conversation() -> None:
    resp = client.post("/conversations")
    assert resp.status_code == 201
    cid = resp.json()["id"]
    assert cid.startswith("conv_")
    assert resp.json()["messages"] == []

    resp = client.get(f"/conversations/{cid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == cid
    assert resp.json()["messages"] == []


def test_append_messages_in_order() -> None:
    cid = client.post("/conversations").json()["id"]
    client.post(
        f"/conversations/{cid}/messages",
        json={"role": "user", "content": "what is 2+2?"},
    )
    resp = client.post(
        f"/conversations/{cid}/messages",
        json={"role": "assistant", "content": "4"},
    )
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert [m["content"] for m in messages] == ["what is 2+2?", "4"]
    assert [m["role"] for m in messages] == ["user", "assistant"]


def test_append_rejects_bad_role() -> None:
    cid = client.post("/conversations").json()["id"]
    resp = client.post(
        f"/conversations/{cid}/messages",
        json={"role": "system", "content": "nope"},
    )
    assert resp.status_code == 422


def test_get_missing_conversation_404() -> None:
    assert client.get("/conversations/nope").status_code == 404
    resp = client.post(
        "/conversations/nope/messages",
        json={"role": "user", "content": "hi"},
    )
    assert resp.status_code == 404


def test_list_conversations_newest_first() -> None:
    client.post("/conversations")
    client.post("/conversations")
    resp = client.get("/conversations")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 2
    assert entries[0]["updated_at"] >= entries[1]["updated_at"]
    assert "message_count" in entries[0]
    assert "preview" in entries[0]


def test_list_shows_first_user_message_as_preview() -> None:
    cid = client.post("/conversations").json()["id"]
    client.post(
        f"/conversations/{cid}/messages",
        json={"role": "user", "content": "resume this chat"},
    )
    client.post(
        f"/conversations/{cid}/messages",
        json={"role": "assistant", "content": "ok"},
    )
    entries = client.get("/conversations").json()
    entry = next(e for e in entries if e["id"] == cid)
    assert entry["preview"] == "resume this chat"
    assert entry["message_count"] == 2


def test_reaper_evicts_idle_but_keeps_fresh() -> None:
    store = ConversationStore(ttl_secs=3600, reap_interval_secs=60)
    idle = store.create()
    fresh = store.create()
    store.append(fresh["id"], "user", "recently active")
    with store._lock:
        store._conversations[idle["id"]]["updated_at"] = 0
    assert store.reap_expired() == 1
    assert store.get(idle["id"]) is None
    assert store.get(fresh["id"]) is not None


def test_reaper_leaves_everything_fresh_untouched() -> None:
    store = ConversationStore(ttl_secs=3600, reap_interval_secs=60)
    store.create()
    store.create()
    assert store.reap_expired() == 0
