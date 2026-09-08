import pytest

from database.queries import delete_chat_messages, get_chat_messages, insert_chat_message

from ai import llm_client
from ai.llm_client import AIConfigError


# ------------------------------------------------------------------ #
# chat_messages query helpers                                        #
# ------------------------------------------------------------------ #

def test_insert_chat_message_creates_row(client):
    message_id = insert_chat_message(1, "user", "hi")

    assert isinstance(message_id, int)
    rows = get_chat_messages(1)
    assert rows[-1]["role"] == "user"
    assert rows[-1]["content"] == "hi"


def test_get_chat_messages_oldest_first(client):
    insert_chat_message(1, "user", "one")
    insert_chat_message(1, "assistant", "two")
    insert_chat_message(1, "user", "three")

    rows = get_chat_messages(1)

    assert len(rows) == 3
    assert [r["content"] for r in rows] == ["one", "two", "three"]
    for row in rows:
        assert set(row.keys()) == {"id", "role", "content", "created_at"}


def test_get_chat_messages_respects_limit(client):
    for i in range(5):
        insert_chat_message(1, "user", "msg%d" % i)

    rows = get_chat_messages(1, limit=2)

    assert [r["content"] for r in rows] == ["msg3", "msg4"]


def test_get_chat_messages_scoped_to_user(client):
    register_new_user(client)
    other_user_id = new_user_id_for(client)

    insert_chat_message(1, "user", "demo user message")
    insert_chat_message(other_user_id, "user", "other user message")

    rows = get_chat_messages(1)

    assert len(rows) == 1
    assert rows[0]["content"] == "demo user message"


def test_delete_chat_messages_scoped_to_user(client):
    register_new_user(client)
    other_user_id = new_user_id_for(client)

    insert_chat_message(1, "user", "a")
    insert_chat_message(1, "assistant", "b")
    insert_chat_message(other_user_id, "user", "c")

    deleted = delete_chat_messages(1)

    assert deleted == 2
    assert get_chat_messages(1) == []
    assert len(get_chat_messages(other_user_id)) == 1


# ------------------------------------------------------------------ #
# ai/llm_client.py                                                    #
# ------------------------------------------------------------------ #

def test_get_client_raises_when_key_unset(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm_client._client = None

    with pytest.raises(AIConfigError) as exc_info:
        llm_client.get_client()

    assert exc_info.value.status == 503
    assert "LLM_API_KEY" in exc_info.value.user_message


def test_create_message_raises_when_key_unset(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm_client._client = None

    with pytest.raises(AIConfigError):
        llm_client.create_message(system_text="You are a test assistant.", turns=[])


def test_map_finish_reason_max_tokens_is_length():
    from google.genai import types

    candidate = types.Candidate.model_validate({"finishReason": "MAX_TOKENS"})

    assert llm_client._map_finish_reason(candidate, has_tool_calls=False) == "length"


def test_map_finish_reason_stop_is_stop():
    from google.genai import types

    candidate = types.Candidate.model_validate({"finishReason": "STOP"})

    assert llm_client._map_finish_reason(candidate, has_tool_calls=False) == "stop"


def test_map_finish_reason_safety_is_refused():
    from google.genai import types

    candidate = types.Candidate.model_validate({"finishReason": "SAFETY"})

    assert llm_client._map_finish_reason(candidate, has_tool_calls=False) == "refused"


def test_map_finish_reason_tool_calls_takes_priority():
    from google.genai import types

    candidate = types.Candidate.model_validate({"finishReason": "STOP"})

    assert llm_client._map_finish_reason(candidate, has_tool_calls=True) == "tool_calls"


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def register_new_user(client, name="New User", email="new@example.com", password="pass1234"):
    client.post(
        "/register",
        data={
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    client.post("/login", data={"email": email, "password": password})


def new_user_id_for(client):
    from database.db import get_user_by_email

    return get_user_by_email("new@example.com")["id"]


# ------------------------------------------------------------------ #
# ai/chat.py — build_messages                                        #
# ------------------------------------------------------------------ #

from datetime import date

from ai.chat import build_messages, build_turn_context, run_chat_turn
from ai.prompts import CHAT_SYSTEM_PROMPT
from tests.conftest import text_reply


def test_build_messages_trims_to_history_limit():
    history = [
        {"role": "assistant" if i % 2 == 0 else "user", "content": "msg%d" % i}
        for i in range(25)
    ]

    turns = build_messages(history, "new question")

    assert len(turns) == 21
    assert turns[0]["role"] == "user"
    assert turns[-1] == {"role": "user", "content": "new question"}


def test_build_messages_drops_leading_assistant_row():
    history = [
        {"role": "assistant" if i % 2 == 0 else "user", "content": "msg%d" % i}
        for i in range(20)
    ]

    turns = build_messages(history, "new question")

    assert turns[0]["role"] == "user"


# ------------------------------------------------------------------ #
# ai/chat.py — build_turn_context                                    #
# ------------------------------------------------------------------ #

def test_build_turn_context_includes_date_and_name():
    context = build_turn_context(user_id=1, user_name="Demo User", today=date(2026, 9, 7))

    assert "Today is 2026-09-07." in context
    assert "Demo User" in context


# ------------------------------------------------------------------ #
# ai/chat.py — run_chat_turn                                         #
# ------------------------------------------------------------------ #

def test_run_chat_turn_returns_reply_text(fake_llm):
    fake_llm.responses.append(text_reply("Hello"))
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "msg%d" % i}
        for i in range(30)
    ]

    result = run_chat_turn(1, history, "hi", "Demo User", date(2026, 9, 7))

    assert result == {"reply": "Hello", "tools_used": []}
    call = fake_llm.calls[0]
    assert call["system_text"] == CHAT_SYSTEM_PROMPT
    assert "Today is" in call["context_text"]
    assert len(call["turns"]) == 21


def test_run_chat_turn_refused_reply(fake_llm):
    fake_llm.responses.append(text_reply("", finish_reason="refused"))

    result = run_chat_turn(1, [], "hi", "Demo User", date(2026, 9, 7))

    assert result["reply"] == "I can't help with that request."


def test_run_chat_turn_length_reply(fake_llm):
    fake_llm.responses.append(text_reply("partial answer", finish_reason="length"))

    result = run_chat_turn(1, [], "hi", "Demo User", date(2026, 9, 7))

    assert result["reply"] == "partial answer …"


def test_run_chat_turn_empty_text_reply(fake_llm):
    fake_llm.responses.append(text_reply(""))

    result = run_chat_turn(1, [], "hi", "Demo User", date(2026, 9, 7))

    assert result["reply"] == "Done."


from ai.llm_client import AIRateLimitError, AIUnavailableError
from tests.conftest import text_reply


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

def test_chat_history_requires_auth(client):
    response = client.get("/api/chat/history")

    assert response.status_code == 401
    assert "error" in response.get_json()


def test_chat_history_returns_stored_messages(client, monkeypatch):
    from database.queries import insert_chat_message

    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    insert_chat_message(1, "user", "hi")
    insert_chat_message(1, "assistant", "hello")

    response = client.get("/api/chat/history")
    body = response.get_json()

    assert response.status_code == 200
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"


def test_chat_send_requires_auth(client):
    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 401


def test_chat_send_success_stores_both_turns(client, fake_llm):
    from database.queries import get_chat_messages

    fake_llm.responses.append(text_reply("Sure"))
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 200
    assert response.get_json() == {"reply": "Sure"}

    rows = get_chat_messages(1)
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "hi"
    assert rows[1]["content"] == "Sure"


def test_chat_send_blank_message(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "   "})

    assert response.status_code == 400
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_send_too_long_message(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "x" * 2001})

    assert response.status_code == 400
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_send_non_json_body(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", data="not json", content_type="text/plain")

    assert response.status_code == 400


def test_chat_send_no_api_key_configured(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    from ai import llm_client
    llm_client._client = None
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 503
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_send_unavailable_error(client, fake_llm):
    fake_llm.responses.append(AIUnavailableError("The assistant is temporarily unavailable. Please try again."))
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 502
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_send_rate_limit_error(client, fake_llm):
    fake_llm.responses.append(AIRateLimitError("The assistant is busy. Please try again in a moment."))
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/api/chat", json={"message": "hi"})

    assert response.status_code == 429
    from database.queries import get_chat_messages
    assert get_chat_messages(1) == []


def test_chat_clear_requires_auth(client):
    response = client.delete("/api/chat/history")

    assert response.status_code == 401


def test_chat_clear_deletes_rows(client):
    from database.queries import insert_chat_message, get_chat_messages

    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    insert_chat_message(1, "user", "a")
    insert_chat_message(1, "assistant", "b")
    insert_chat_message(1, "user", "c")

    response = client.delete("/api/chat/history")

    assert response.status_code == 200
    assert response.get_json() == {"cleared": 3}
    assert get_chat_messages(1) == []


# ------------------------------------------------------------------ #
# Task 5: Chat drawer UI                                             #
# ------------------------------------------------------------------ #

def test_profile_includes_chat_drawer_when_logged_in(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="chat-drawer"' in body
    assert "js/chat.js" in body


def test_landing_excludes_chat_drawer_when_logged_out(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "chat-drawer" not in body
