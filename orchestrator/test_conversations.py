from fastapi.testclient import TestClient

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
