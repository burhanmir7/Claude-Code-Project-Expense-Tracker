import json
from datetime import date
from types import SimpleNamespace

import pytest

import ai.tools.registry as tools_registry
from ai.chat import run_chat_turn
from ai.tools import execute_tool, get_tool_definitions, is_mutating
from database.db import CATEGORIES, get_db, get_user_by_email
from database.queries import get_chat_messages, get_expense_by_id, insert_expense

from tests.conftest import text_reply, tool_call_reply


# ------------------------------------------------------------------ #
# Helpers                                                             #
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


def new_user_id_for(client, email="new@example.com"):
    return get_user_by_email(email)["id"]


def login_demo(client):
    client.get("/logout")
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})


# ------------------------------------------------------------------ #
# ai/tools — get_tool_definitions                                    #
# ------------------------------------------------------------------ #

def test_get_tool_definitions_order_and_names(client):
    names = [d["name"] for d in get_tool_definitions()]

    assert names == [
        "list_expenses", "add_expense", "update_expense", "delete_expense",
        "list_accounts", "get_net_worth", "add_account", "update_account_balance",
        "delete_account",
    ]


def test_get_tool_definitions_schema_shape(client):
    for definition in get_tool_definitions():
        schema = definition["input_schema"]
        name = definition["name"]

        assert schema["additionalProperties"] is False, "%s must set additionalProperties: false" % name

        properties = set(schema["properties"].keys())
        required = set(schema["required"])
        assert properties == required, "%s must require every declared property" % name
        assert "user_id" not in properties, "%s must never expose user_id to the model" % name


def test_add_expense_category_enum_matches_categories(client):
    add_expense_def = next(d for d in get_tool_definitions() if d["name"] == "add_expense")

    assert add_expense_def["input_schema"]["properties"]["category"]["enum"] == CATEGORIES


# ------------------------------------------------------------------ #
# ai/tools — is_mutating                                             #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "name,expected",
    [
        ("list_expenses", False),
        ("add_expense", True),
        ("update_expense", True),
        ("delete_expense", True),
        ("not_a_real_tool", False),
    ],
)
def test_is_mutating(name, expected):
    assert is_mutating(name) is expected


# ------------------------------------------------------------------ #
# ai/tools — execute_tool: add_expense                                #
# ------------------------------------------------------------------ #

def test_execute_tool_add_expense_valid_creates_row(client):
    content, is_error = execute_tool(
        "add_expense",
        {"amount": 100, "category": "Food", "date": "2026-09-01", "description": "Snacks"},
        1,
    )

    assert is_error is False
    payload = json.loads(content)
    assert payload["ok"] is True

    row = get_expense_by_id(payload["expense"]["id"], 1)
    assert row is not None, "expected the new expense to belong to user 1"
    assert row["amount"] == 100
    assert row["category"] == "Food"
    assert row["date"] == "2026-09-01"
    assert row["description"] == "Snacks"


def test_execute_tool_add_expense_negative_amount_is_error(client):
    conn = get_db()
    before = conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"]
    conn.close()

    content, is_error = execute_tool(
        "add_expense",
        {"amount": -5, "category": "Food", "date": "2026-09-01", "description": None},
        1,
    )

    assert is_error is True
    assert "error" in json.loads(content)

    conn = get_db()
    after = conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"]
    conn.close()
    assert after == before, "an invalid amount must not insert a row"


def test_execute_tool_add_expense_invalid_category_is_error(client):
    content, is_error = execute_tool(
        "add_expense",
        {"amount": 20, "category": "Rent", "date": "2026-09-01", "description": None},
        1,
    )

    assert is_error is True
    assert "error" in json.loads(content)


def test_execute_tool_add_expense_ignores_extra_user_id_key(client):
    content, is_error = execute_tool(
        "add_expense",
        {
            "amount": 40,
            "category": "Food",
            "date": "2026-09-01",
            "description": None,
            "user_id": 2,
        },
        1,
    )

    assert is_error is False
    expense_id = json.loads(content)["expense"]["id"]

    assert get_expense_by_id(expense_id, 1) is not None, "row should be created for the real caller (user 1)"
    assert get_expense_by_id(expense_id, 2) is None, "the smuggled user_id must be ignored"


# ------------------------------------------------------------------ #
# ai/tools — execute_tool: update_expense                             #
# ------------------------------------------------------------------ #

def test_execute_tool_update_expense_partial_update_keeps_other_fields(client):
    expense_id = insert_expense(1, 50, "Food", "2026-09-01", "Lunch")

    content, is_error = execute_tool(
        "update_expense",
        {"expense_id": expense_id, "amount": 75, "category": None, "date": None, "description": None},
        1,
    )

    assert is_error is False
    row = get_expense_by_id(expense_id, 1)
    assert row["amount"] == 75
    assert row["category"] == "Food"
    assert row["date"] == "2026-09-01"
    assert row["description"] == "Lunch"


def test_execute_tool_update_expense_cross_user_is_error(client):
    register_new_user(client)
    other_id = new_user_id_for(client)
    expense_id = insert_expense(other_id, 50, "Food", "2026-09-01", "Lunch")

    content, is_error = execute_tool(
        "update_expense",
        {"expense_id": expense_id, "amount": 999, "category": None, "date": None, "description": None},
        1,
    )

    assert is_error is True
    assert "error" in json.loads(content)

    row = get_expense_by_id(expense_id, other_id)
    assert row["amount"] == 50, "another user's expense must be unaffected"


# ------------------------------------------------------------------ #
# ai/tools — execute_tool: delete_expense                             #
# ------------------------------------------------------------------ #

def test_execute_tool_delete_expense_own_id_removes_row(client):
    expense_id = insert_expense(1, 20, "Food", "2026-09-01", "Snack")

    content, is_error = execute_tool("delete_expense", {"expense_id": expense_id}, 1)

    assert is_error is False
    assert get_expense_by_id(expense_id, 1) is None


def test_execute_tool_delete_expense_cross_user_is_error(client):
    register_new_user(client)
    other_id = new_user_id_for(client)
    expense_id = insert_expense(other_id, 20, "Food", "2026-09-01", "Snack")

    content, is_error = execute_tool("delete_expense", {"expense_id": expense_id}, 1)

    assert is_error is True
    assert "error" in json.loads(content)
    assert get_expense_by_id(expense_id, other_id) is not None, "another user's expense must remain"


# ------------------------------------------------------------------ #
# ai/tools — execute_tool: list_expenses                              #
# ------------------------------------------------------------------ #

def test_execute_tool_list_expenses_filters_by_category_and_owner(client):
    register_new_user(client)
    other_id = new_user_id_for(client)
    insert_expense(1, 10, "Food", "2026-09-01", "Mine food")
    insert_expense(1, 20, "Transport", "2026-09-01", "Mine transport")
    insert_expense(other_id, 30, "Food", "2026-09-01", "Other food")

    content, is_error = execute_tool(
        "list_expenses",
        {"date_from": None, "date_to": None, "category": "Food", "limit": 50},
        1,
    )

    assert is_error is False
    expenses = json.loads(content)["expenses"]
    descriptions = [e["description"] for e in expenses]

    assert all(e["category"] == "Food" for e in expenses)
    assert "Mine food" in descriptions
    assert "Other food" not in descriptions
    assert "Mine transport" not in descriptions


def test_execute_tool_list_expenses_only_date_from_includes_matching(client):
    insert_expense(1, 15, "Food", "2026-01-01", "Old one")
    insert_expense(1, 25, "Food", "2026-12-31", "New one")

    content, is_error = execute_tool(
        "list_expenses",
        {"date_from": "2026-06-01", "date_to": None, "category": None, "limit": 50},
        1,
    )

    assert is_error is False
    dates = [e["date"] for e in json.loads(content)["expenses"]]

    assert "2026-12-31" in dates
    assert "2026-01-01" not in dates


def test_execute_tool_unknown_name_is_error_no_exception(client):
    content, is_error = execute_tool("delete_everything", {}, 1)

    assert is_error is True
    assert "error" in json.loads(content)


def test_execute_tool_handler_exception_is_caught_and_returns_error(client, monkeypatch):
    def _raising_handler(user_id, tool_input):
        raise RuntimeError("boom")

    monkeypatch.setitem(tools_registry._TOOLS["list_expenses"], "handler", _raising_handler)

    content, is_error = execute_tool(
        "list_expenses",
        {"date_from": None, "date_to": None, "category": None, "limit": 5},
        1,
    )

    assert is_error is True
    assert "error" in json.loads(content)


# ------------------------------------------------------------------ #
# ai/chat.py — run_chat_turn tool loop                                #
# ------------------------------------------------------------------ #

def test_run_chat_turn_executes_tool_then_returns_final_text(client, fake_llm):
    fake_llm.responses.append(
        tool_call_reply(
            "add_expense",
            {"amount": 250, "category": "Food", "date": "2026-09-10", "description": "Lunch"},
        )
    )
    fake_llm.responses.append(text_reply("Added ₹250"))

    result = run_chat_turn(1, [], "add 250 for lunch today", "Demo User", date(2026, 9, 10))

    assert result["reply"] == "Added ₹250"
    assert result["tools_used"] == ["add_expense"]

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? AND description = ?", (1, "Lunch")
    ).fetchone()
    conn.close()
    assert row is not None

    second_call = fake_llm.calls[1]
    tool_result_entries = [t for t in second_call["turns"] if t["role"] == "tool_result"]
    assert len(tool_result_entries) == 1
    assert second_call["tools"], "the follow-up call must still advertise tool definitions"


def test_run_chat_turn_two_tool_calls_in_one_round(client, fake_llm):
    call_a = SimpleNamespace(
        id="call_a",
        name="list_expenses",
        input={"date_from": None, "date_to": None, "category": None, "limit": 5},
    )
    call_b = SimpleNamespace(
        id="call_b",
        name="list_expenses",
        input={"date_from": None, "date_to": None, "category": "Food", "limit": 5},
    )
    two_call_reply = SimpleNamespace(text="", tool_calls=[call_a, call_b], finish_reason="tool_calls")
    fake_llm.responses.append(two_call_reply)
    fake_llm.responses.append(text_reply("Here you go"))

    result = run_chat_turn(1, [], "show me expenses", "Demo User", date(2026, 9, 10))

    assert result["reply"] == "Here you go"
    assert result["tools_used"] == ["list_expenses", "list_expenses"]

    second_call = fake_llm.calls[1]
    tool_result_entries = [t for t in second_call["turns"] if t["role"] == "tool_result"]
    assert len(tool_result_entries) == 2
    assert {t["tool_call_id"] for t in tool_result_entries} == {"call_a", "call_b"}


def test_run_chat_turn_stops_after_max_rounds(client, fake_llm):
    for i in range(9):
        fake_llm.responses.append(
            tool_call_reply(
                "list_expenses",
                {"date_from": None, "date_to": None, "category": None, "limit": 1},
                tool_id="call_%d" % i,
            )
        )

    result = run_chat_turn(1, [], "loop forever", "Demo User", date(2026, 9, 10))

    assert result["reply"] == "I couldn't finish that request. Please try a simpler instruction."
    assert len(fake_llm.calls) == 9, "8 rounds means 9 create_message calls (the 9th just breaks the loop)"
    assert len(result["tools_used"]) == 8


def test_run_chat_turn_tool_handler_raises_continues_loop(client, fake_llm, monkeypatch):
    def _raising_handler(user_id, tool_input):
        raise RuntimeError("boom")

    monkeypatch.setitem(tools_registry._TOOLS["add_expense"], "handler", _raising_handler)

    fake_llm.responses.append(
        tool_call_reply(
            "add_expense",
            {"amount": 10, "category": "Food", "date": "2026-09-10", "description": None},
        )
    )
    fake_llm.responses.append(text_reply("Sorted"))

    result = run_chat_turn(1, [], "add something", "Demo User", date(2026, 9, 10))

    assert result["reply"] == "Sorted"
    assert result["tools_used"] == ["add_expense"]

    second_call = fake_llm.calls[1]
    tool_result_entries = [t for t in second_call["turns"] if t["role"] == "tool_result"]
    assert len(tool_result_entries) == 1
    assert tool_result_entries[0]["is_error"] is True


# ------------------------------------------------------------------ #
# Routes — POST /api/chat                                             #
# ------------------------------------------------------------------ #

def test_chat_send_add_expense_sets_refresh_true(client, fake_llm):
    fake_llm.responses.append(
        tool_call_reply(
            "add_expense",
            {"amount": 250, "category": "Food", "date": "2026-09-10", "description": "Lunch"},
        )
    )
    fake_llm.responses.append(text_reply("Added ₹250 for lunch."))
    login_demo(client)

    response = client.post("/api/chat", json={"message": "add 250 for lunch today"})
    body = response.get_json()

    assert response.status_code == 200
    assert body["refresh"] is True
    assert body["reply"] == "Added ₹250 for lunch."

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? AND description = ?", (1, "Lunch")
    ).fetchone()
    conn.close()
    assert row is not None, "the new expense must belong to the logged-in user"

    rows = get_chat_messages(1)
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert len(rows) == 2, "only the user turn and final assistant turn are persisted"
    assert rows[0]["content"] == "add 250 for lunch today"
    assert rows[1]["content"] == "Added ₹250 for lunch."


def test_chat_send_text_only_reply_sets_refresh_false(client, fake_llm):
    fake_llm.responses.append(text_reply("Sure, here's the info."))
    login_demo(client)

    response = client.post("/api/chat", json={"message": "hello"})
    body = response.get_json()

    assert response.status_code == 200
    assert body["refresh"] is False


def test_chat_send_delete_cross_user_expense_is_protected(client, fake_llm):
    expense_id = insert_expense(1, 40, "Food", "2026-09-01", "User A lunch")

    register_new_user(client)  # now logged in as a different user
    fake_llm.responses.append(tool_call_reply("delete_expense", {"expense_id": expense_id}))
    fake_llm.responses.append(text_reply("I couldn't find that expense."))

    response = client.post("/api/chat", json={"message": "delete expense %d" % expense_id})

    assert response.status_code == 200
    assert get_expense_by_id(expense_id, 1) is not None, "user A's expense must survive user B's attempt"


def test_chat_send_list_expenses_tool_result_scoped_to_user(client, fake_llm):
    register_new_user(client)
    other_id = new_user_id_for(client)
    login_demo(client)

    insert_expense(1, 15, "Food", "2026-09-01", "Mine")
    insert_expense(other_id, 15, "Food", "2026-09-01", "Not mine")

    fake_llm.responses.append(
        tool_call_reply(
            "list_expenses",
            {"date_from": None, "date_to": None, "category": "Food", "limit": 50},
        )
    )
    fake_llm.responses.append(text_reply("Here are your food expenses."))

    client.post("/api/chat", json={"message": "show my food expenses"})

    second_call = fake_llm.calls[1]
    tool_result = next(t for t in second_call["turns"] if t["role"] == "tool_result")
    descriptions = [e["description"] for e in json.loads(tool_result["content"])["expenses"]]

    assert "Mine" in descriptions
    assert "Not mine" not in descriptions


def test_chat_send_unknown_tool_name_returns_200_with_tool_error(client, fake_llm):
    login_demo(client)

    fake_llm.responses.append(tool_call_reply("delete_everything", {}))
    fake_llm.responses.append(text_reply("Sorry, I can't do that."))

    response = client.post("/api/chat", json={"message": "wipe my account"})

    assert response.status_code == 200
    second_call = fake_llm.calls[1]
    tool_result = next(t for t in second_call["turns"] if t["role"] == "tool_result")
    assert tool_result["is_error"] is True
