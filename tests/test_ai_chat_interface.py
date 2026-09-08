from database.queries import delete_chat_messages, get_chat_messages, insert_chat_message


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
