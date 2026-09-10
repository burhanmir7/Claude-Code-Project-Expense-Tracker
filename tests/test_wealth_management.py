import json
from datetime import date

from ai.chat import build_turn_context
from ai.tools import execute_tool, get_tool_definitions
from ai.tools.accounts import _validate_account_fields, net_worth_context
from database.db import ACCOUNT_TYPES, get_db, get_user_by_email
from database.queries import (
    delete_account_by_id,
    get_account_by_id,
    get_accounts,
    get_net_worth,
    insert_account,
    update_account,
)

from tests.conftest import register_new_user, text_reply, tool_call_reply

DEMO_USER_ID = 1


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def login_demo(client):
    client.get("/logout")
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})


def new_user_id_for(client, email="new@example.com"):
    return get_user_by_email(email)["id"]


# ------------------------------------------------------------------ #
# database/queries.py — insert_account                                #
# ------------------------------------------------------------------ #

def test_insert_account_returns_id_and_persists_row(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    assert isinstance(account_id, int)
    conn = get_db()
    row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    conn.close()

    assert row is not None
    assert row["user_id"] == DEMO_USER_ID
    assert row["name"] == "HDFC Savings"
    assert row["type"] == "savings"
    assert row["balance"] == 50000


# ------------------------------------------------------------------ #
# database/queries.py — get_accounts                                  #
# ------------------------------------------------------------------ #

def test_get_accounts_scoped_to_user_and_ordered_by_type_then_name(client):
    register_new_user(client)
    other_id = new_user_id_for(client)

    insert_account(DEMO_USER_ID, "Zeta Savings", "savings", 100)
    insert_account(DEMO_USER_ID, "Alpha Debt", "debt", 200)
    insert_account(other_id, "Other Account", "savings", 300)

    accounts = get_accounts(DEMO_USER_ID)

    assert len(accounts) == 2, "only user 1's accounts should be returned"
    assert [a["type"] for a in accounts] == ["debt", "savings"], "ordered by type"
    assert [a["name"] for a in accounts] == ["Alpha Debt", "Zeta Savings"]


# ------------------------------------------------------------------ #
# database/queries.py — get_account_by_id                             #
# ------------------------------------------------------------------ #

def test_get_account_by_id_returns_dict_for_owner(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    account = get_account_by_id(account_id, DEMO_USER_ID)

    assert account["name"] == "HDFC Savings"
    assert account["type"] == "savings"
    assert account["balance"] == 50000


def test_get_account_by_id_returns_none_for_other_user(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    assert get_account_by_id(account_id, DEMO_USER_ID + 999) is None


def test_get_account_by_id_returns_none_for_nonexistent_id(client):
    assert get_account_by_id(999999, DEMO_USER_ID) is None


# ------------------------------------------------------------------ #
# database/queries.py — update_account                                #
# ------------------------------------------------------------------ #

def test_update_account_updates_balance_for_owner(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)
    conn = get_db()
    before = conn.execute(
        "SELECT created_at FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    conn.close()

    rowcount = update_account(account_id, DEMO_USER_ID, "HDFC Savings", "savings", 60000)

    assert rowcount == 1
    conn = get_db()
    after = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    conn.close()

    assert after["balance"] == 60000
    assert after["updated_at"] >= before["created_at"], "updated_at must not be earlier than created_at"


def test_update_account_no_effect_for_other_user(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    rowcount = update_account(account_id, DEMO_USER_ID + 999, "Renamed", "debt", 1)

    assert rowcount == 0
    row = get_account_by_id(account_id, DEMO_USER_ID)
    assert row["name"] == "HDFC Savings", "row must be unchanged"
    assert row["balance"] == 50000


# ------------------------------------------------------------------ #
# database/queries.py — delete_account_by_id                          #
# ------------------------------------------------------------------ #

def test_delete_account_by_id_removes_row_for_owner(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    rowcount = delete_account_by_id(account_id, DEMO_USER_ID)

    assert rowcount == 1
    assert get_account_by_id(account_id, DEMO_USER_ID) is None


def test_delete_account_by_id_no_effect_for_other_user(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    rowcount = delete_account_by_id(account_id, DEMO_USER_ID + 999)

    assert rowcount == 0
    assert get_account_by_id(account_id, DEMO_USER_ID) is not None, "row must remain"


# ------------------------------------------------------------------ #
# database/queries.py — get_net_worth                                 #
# ------------------------------------------------------------------ #

def test_get_net_worth_computes_assets_debts_and_net_worth(client):
    insert_account(DEMO_USER_ID, "Savings", "savings", 50000)
    insert_account(DEMO_USER_ID, "Stocks", "investment", 20000)
    insert_account(DEMO_USER_ID, "Loan", "debt", 30000)

    net = get_net_worth(DEMO_USER_ID)

    assert net["assets"] == 70000
    assert net["debts"] == 30000
    assert net["net_worth"] == 40000
    assert net["account_count"] == 3


def test_get_net_worth_all_zero_when_no_accounts(client):
    net = get_net_worth(DEMO_USER_ID)

    assert net["assets"] == 0
    assert net["debts"] == 0
    assert net["net_worth"] == 0
    assert net["account_count"] == 0


# ------------------------------------------------------------------ #
# ai/tools/accounts.py — _validate_account_fields                     #
# ------------------------------------------------------------------ #

def test_validate_account_fields_name_too_long_returns_error(client):
    error = _validate_account_fields("x" * 61, "savings", 100)

    assert error is not None
    assert "60" in error


def test_validate_account_fields_negative_balance_returns_error(client):
    error = _validate_account_fields("Savings", "savings", -1)

    assert error is not None
    assert "balance" in error.lower()


def test_validate_account_fields_valid_input_returns_none(client):
    assert _validate_account_fields("Savings", "savings", 0) is None


# ------------------------------------------------------------------ #
# ai/tools — execute_tool: add_account                                #
# ------------------------------------------------------------------ #

def test_execute_tool_add_account_valid_creates_row(client):
    content, is_error = execute_tool(
        "add_account",
        {"name": "HDFC Savings", "type": "savings", "balance": 50000},
        DEMO_USER_ID,
    )

    assert is_error is False
    payload = json.loads(content)
    assert payload["ok"] is True

    row = get_account_by_id(payload["account"]["id"], DEMO_USER_ID)
    assert row is not None, "expected the new account to belong to the caller"
    assert row["name"] == "HDFC Savings"
    assert row["type"] == "savings"
    assert row["balance"] == 50000


def test_execute_tool_add_account_invalid_type_is_error(client):
    conn = get_db()
    before = conn.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()["c"]
    conn.close()

    content, is_error = execute_tool(
        "add_account",
        {"name": "Crypto Wallet", "type": "crypto", "balance": 100},
        DEMO_USER_ID,
    )

    assert is_error is True
    assert "error" in json.loads(content)

    conn = get_db()
    after = conn.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()["c"]
    conn.close()
    assert after == before, "an invalid account type must not insert a row"


# ------------------------------------------------------------------ #
# ai/tools — execute_tool: update_account_balance                     #
# ------------------------------------------------------------------ #

def test_execute_tool_update_account_balance_cross_user_is_error(client):
    register_new_user(client)
    other_id = new_user_id_for(client)
    account_id = insert_account(other_id, "Other Savings", "savings", 1000)

    content, is_error = execute_tool(
        "update_account_balance",
        {"account_id": account_id, "balance": 9999},
        DEMO_USER_ID,
    )

    assert is_error is True
    assert "error" in json.loads(content)

    row = get_account_by_id(account_id, other_id)
    assert row["balance"] == 1000, "another user's account balance must be unaffected"


# ------------------------------------------------------------------ #
# ai/tools — execute_tool: delete_account                              #
# ------------------------------------------------------------------ #

def test_execute_tool_delete_account_valid_removes_row(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    content, is_error = execute_tool("delete_account", {"account_id": account_id}, DEMO_USER_ID)

    assert is_error is False
    payload = json.loads(content)
    assert payload["ok"] is True
    assert get_account_by_id(account_id, DEMO_USER_ID) is None


def test_execute_tool_delete_account_cross_user_is_error(client):
    register_new_user(client)
    other_id = new_user_id_for(client)
    account_id = insert_account(other_id, "Other Savings", "savings", 1000)

    content, is_error = execute_tool("delete_account", {"account_id": account_id}, DEMO_USER_ID)

    assert is_error is True
    assert "error" in json.loads(content)
    assert get_account_by_id(account_id, other_id) is not None, "another user's account must survive"


def test_execute_tool_delete_account_unknown_id_is_error(client):
    content, is_error = execute_tool("delete_account", {"account_id": 999999}, DEMO_USER_ID)

    assert is_error is True
    assert "error" in json.loads(content)


# ------------------------------------------------------------------ #
# ai/tools — execute_tool: get_net_worth                               #
# ------------------------------------------------------------------ #

def test_execute_tool_get_net_worth_returns_json_with_net_worth(client):
    insert_account(DEMO_USER_ID, "Savings", "savings", 1000)

    content, is_error = execute_tool("get_net_worth", {}, DEMO_USER_ID)

    assert is_error is False
    payload = json.loads(content)
    assert "net_worth" in payload
    assert payload["net_worth"] == 1000


# ------------------------------------------------------------------ #
# ai/tools/accounts.py — net_worth_context                             #
# ------------------------------------------------------------------ #

def test_net_worth_context_with_accounts_contains_snapshot_and_rupee(client):
    insert_account(DEMO_USER_ID, "Savings", "savings", 1000)

    context = net_worth_context(DEMO_USER_ID)

    assert context is not None
    assert "Net worth snapshot" in context
    assert "₹" in context


def test_net_worth_context_without_accounts_returns_none(client):
    assert net_worth_context(DEMO_USER_ID) is None


# ------------------------------------------------------------------ #
# ai/chat.py — build_turn_context                                     #
# ------------------------------------------------------------------ #

def test_build_turn_context_includes_net_worth_snapshot_when_accounts_exist(client):
    insert_account(DEMO_USER_ID, "Savings", "savings", 1000)

    context = build_turn_context(user_id=DEMO_USER_ID, user_name="Demo User", today=date(2026, 9, 10))

    assert "Net worth snapshot" in context


def test_build_turn_context_omits_net_worth_snapshot_when_no_accounts(client):
    context = build_turn_context(user_id=DEMO_USER_ID, user_name="Demo User", today=date(2026, 9, 10))

    assert "Net worth snapshot" not in context


# ------------------------------------------------------------------ #
# ai/tools — get_tool_definitions                                     #
# ------------------------------------------------------------------ #

def test_get_tool_definitions_includes_account_tools_in_full_order(client):
    names = [d["name"] for d in get_tool_definitions()]

    assert names == [
        "list_expenses", "add_expense", "update_expense", "delete_expense",
        "list_accounts", "get_net_worth", "add_account", "update_account_balance",
        "delete_account",
    ]


def test_add_account_tool_schema_type_enum_matches_account_types(client):
    add_account_def = next(d for d in get_tool_definitions() if d["name"] == "add_account")

    assert add_account_def["input_schema"]["properties"]["type"]["enum"] == ACCOUNT_TYPES


# ------------------------------------------------------------------ #
# Routes — GET /accounts                                              #
# ------------------------------------------------------------------ #

def test_accounts_get_unauthenticated_redirects_to_login(client):
    response = client.get("/accounts")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_accounts_get_authenticated_lists_accounts_and_net_worth(client):
    login_demo(client)
    insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)
    insert_account(DEMO_USER_ID, "Mutual Funds", "investment", 20000)
    insert_account(DEMO_USER_ID, "Car Loan", "debt", 30000)

    response = client.get("/accounts")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "HDFC Savings" in body
    assert "Mutual Funds" in body
    assert "Car Loan" in body
    assert "₹40,000.00" in body, "net worth = 70000 assets - 30000 debts"
    assert 'aria-label="Edit account"' in body
    assert 'aria-label="Delete account"' in body


def test_accounts_get_authenticated_no_accounts_shows_empty_state(client):
    login_demo(client)

    response = client.get("/accounts")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No accounts yet." in body


# ------------------------------------------------------------------ #
# Routes — GET, POST /accounts/add                                    #
# ------------------------------------------------------------------ #

def test_accounts_add_get_unauthenticated_redirects(client):
    response = client.get("/accounts/add")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_accounts_add_post_unauthenticated_redirects(client):
    response = client.post(
        "/accounts/add", data={"name": "X", "type": "savings", "balance": "1"}
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_accounts_add_post_valid_redirects_and_creates_row(client):
    login_demo(client)

    response = client.post(
        "/accounts/add",
        data={"name": "HDFC Savings", "type": "savings", "balance": "50000"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/accounts")

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM accounts WHERE user_id = ? ORDER BY id DESC LIMIT 1", (DEMO_USER_ID,)
    ).fetchone()
    conn.close()

    assert row["name"] == "HDFC Savings"
    assert row["type"] == "savings"
    assert row["balance"] == 50000


def test_accounts_add_post_missing_name_returns_400(client):
    login_demo(client)

    response = client.post(
        "/accounts/add", data={"name": "", "type": "savings", "balance": "1000"}
    )

    assert response.status_code == 400
    assert "required" in response.get_data(as_text=True).lower()


def test_accounts_add_post_invalid_type_returns_400_and_retains_name(client):
    login_demo(client)

    response = client.post(
        "/accounts/add",
        data={"name": "Crypto Wallet", "type": "crypto", "balance": "100"},
    )

    assert response.status_code == 400
    assert 'value="Crypto Wallet"' in response.get_data(as_text=True)


def test_accounts_add_post_negative_balance_returns_400(client):
    login_demo(client)

    response = client.post(
        "/accounts/add", data={"name": "Savings", "type": "savings", "balance": "-1"}
    )

    assert response.status_code == 400


# ------------------------------------------------------------------ #
# Routes — GET, POST /accounts/<id>/edit                              #
# ------------------------------------------------------------------ #

def test_accounts_edit_get_unauthenticated_redirects(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    response = client.get(f"/accounts/{account_id}/edit")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_accounts_edit_get_other_users_account_returns_404(client):
    register_new_user(client)
    other_id = new_user_id_for(client)
    account_id = insert_account(other_id, "Other Savings", "savings", 1000)

    client.get("/logout")
    login_demo(client)

    response = client.get(f"/accounts/{account_id}/edit")

    assert response.status_code == 404


def test_accounts_edit_get_nonexistent_id_returns_404(client):
    login_demo(client)

    response = client.get("/accounts/999999/edit")

    assert response.status_code == 404


def test_accounts_edit_post_valid_updates_db(client):
    login_demo(client)
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    response = client.post(
        f"/accounts/{account_id}/edit",
        data={"name": "HDFC Prime Savings", "type": "savings", "balance": "75000"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/accounts")

    row = get_account_by_id(account_id, DEMO_USER_ID)
    assert row["name"] == "HDFC Prime Savings"
    assert row["balance"] == 75000


def test_accounts_edit_post_other_users_account_returns_404(client):
    register_new_user(client)
    other_id = new_user_id_for(client)
    account_id = insert_account(other_id, "Other Savings", "savings", 1000)

    client.get("/logout")
    login_demo(client)

    response = client.post(
        f"/accounts/{account_id}/edit",
        data={"name": "Hijacked", "type": "debt", "balance": "1"},
    )

    assert response.status_code == 404
    row = get_account_by_id(account_id, other_id)
    assert row["name"] == "Other Savings", "another user's account must be unaffected"


# ------------------------------------------------------------------ #
# Routes — POST /accounts/<id>/delete                                 #
# ------------------------------------------------------------------ #

def test_accounts_delete_post_unauthenticated_redirects(client):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    response = client.post(f"/accounts/{account_id}/delete")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_accounts_delete_post_own_account_redirects_and_removes_row(client):
    login_demo(client)
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    response = client.post(f"/accounts/{account_id}/delete")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/accounts")
    assert get_account_by_id(account_id, DEMO_USER_ID) is None


def test_accounts_delete_post_other_users_account_returns_404_and_row_remains(client):
    register_new_user(client)
    other_id = new_user_id_for(client)
    account_id = insert_account(other_id, "Other Savings", "savings", 1000)

    client.get("/logout")
    login_demo(client)

    response = client.post(f"/accounts/{account_id}/delete")

    assert response.status_code == 404
    assert get_account_by_id(account_id, other_id) is not None


def test_accounts_delete_get_unauthenticated_returns_405(client):
    response = client.get("/accounts/1/delete")

    assert response.status_code == 405


# ------------------------------------------------------------------ #
# Routes — GET /profile (account balance card)                        #
# ------------------------------------------------------------------ #

def test_profile_with_accounts_shows_balance_card(client):
    login_demo(client)
    insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)
    insert_account(DEMO_USER_ID, "Mutual Funds", "investment", 20000)
    insert_account(DEMO_USER_ID, "Car Loan", "debt", 30000)

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Account Balance" in body
    assert "HDFC Savings" in body
    assert "₹50,000.00" in body, "Account Balance is savings-only: debt and investment accounts have their own cards"
    assert 'id="profile-balance-toggle"' in body
    assert 'href="/accounts"' in body, "Accounts nav link must be present on the sidebar layout"


def test_profile_with_debt_account_shows_debt_card(client):
    login_demo(client)
    insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)
    insert_account(DEMO_USER_ID, "Car Loan", "debt", 30000)
    insert_account(DEMO_USER_ID, "Personal Loan", "debt", 10000)

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Debt" in body
    assert "Car Loan" in body
    assert "Personal Loan" in body
    assert "₹40,000.00" in body, "Debt card is the raw sum of debt accounts only: 30000 + 10000"
    assert "₹50,000.00" in body, "Account Balance shows only the savings account, excluding debt"
    assert 'id="profile-debt-toggle"' in body


def test_profile_with_no_debt_accounts_shows_debt_empty_state(client):
    login_demo(client)
    insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No debts yet." in body
    assert 'id="profile-debt-toggle"' not in body, "the debt selector is omitted with zero debt accounts"


def test_profile_with_no_accounts_shows_empty_state(client):
    login_demo(client)

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Account Balance" in body
    assert "No accounts yet." in body
    assert 'id="profile-balance-toggle"' not in body, "the selector is omitted with zero accounts"


def test_profile_with_investment_account_shows_investment_card(client):
    login_demo(client)
    insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)
    insert_account(DEMO_USER_ID, "Mutual Funds", "investment", 20000)
    insert_account(DEMO_USER_ID, "Index Fund", "investment", 15000)

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Total Investment" in body
    assert "Mutual Funds" in body
    assert "Index Fund" in body
    assert "₹35,000.00" in body, "Total Investment is the raw sum of investment accounts only: 20000 + 15000"
    assert "₹50,000.00" in body, "Account Balance shows only the savings account, excluding investments"
    assert 'id="profile-investment-toggle"' in body


def test_profile_with_no_investment_accounts_shows_investment_empty_state(client):
    login_demo(client)
    insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No investments yet." in body
    assert 'id="profile-investment-toggle"' not in body, "the investment selector is omitted with zero investment accounts"


# ------------------------------------------------------------------ #
# Routes — POST /api/chat (account tools + net-worth context)         #
# ------------------------------------------------------------------ #

def test_chat_update_account_balance_sets_refresh_true_and_updates_db(client, fake_llm):
    login_demo(client)
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    fake_llm.responses.append(
        tool_call_reply("update_account_balance", {"account_id": account_id, "balance": 60000})
    )
    fake_llm.responses.append(text_reply("Updated your HDFC Savings balance to ₹60000."))

    response = client.post("/api/chat", json={"message": "update my HDFC savings to 60000"})
    body = response.get_json()

    assert response.status_code == 200
    assert body["refresh"] is True

    row = get_account_by_id(account_id, DEMO_USER_ID)
    assert row["balance"] == 60000

    first_call = fake_llm.calls[0]
    assert "Net worth snapshot" in first_call["context_text"]


def test_chat_delete_account_sets_refresh_true_and_removes_row(client, fake_llm):
    login_demo(client)
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    fake_llm.responses.append(tool_call_reply("delete_account", {"account_id": account_id}))
    fake_llm.responses.append(text_reply("Your HDFC Savings account has been deleted."))

    response = client.post("/api/chat", json={"message": "yes, delete it"})
    body = response.get_json()

    assert response.status_code == 200
    assert body["refresh"] is True
    assert get_account_by_id(account_id, DEMO_USER_ID) is None


def test_chat_delete_account_cross_user_is_protected(client, fake_llm):
    register_new_user(client)
    other_id = new_user_id_for(client)
    account_id = insert_account(other_id, "Other Savings", "savings", 1000)

    login_demo(client)
    fake_llm.responses.append(tool_call_reply("delete_account", {"account_id": account_id}))
    fake_llm.responses.append(text_reply("I couldn't find that account."))

    response = client.post("/api/chat", json={"message": "delete account %d" % account_id})

    assert response.status_code == 200
    assert get_account_by_id(account_id, other_id) is not None, "another user's account must survive"


def test_chat_context_omits_net_worth_snapshot_when_no_accounts(client, fake_llm):
    login_demo(client)
    fake_llm.responses.append(text_reply("You have no accounts yet."))

    client.post("/api/chat", json={"message": "what's my net worth?"})

    first_call = fake_llm.calls[0]
    assert "Net worth snapshot" not in first_call["context_text"]


def test_chat_update_account_balance_cross_user_is_protected(client, fake_llm):
    account_id = insert_account(DEMO_USER_ID, "HDFC Savings", "savings", 50000)

    register_new_user(client)  # now logged in as a different user
    fake_llm.responses.append(
        tool_call_reply("update_account_balance", {"account_id": account_id, "balance": 1})
    )
    fake_llm.responses.append(text_reply("I couldn't find that account."))

    response = client.post("/api/chat", json={"message": "update account %d" % account_id})

    assert response.status_code == 200
    row = get_account_by_id(account_id, DEMO_USER_ID)
    assert row["balance"] == 50000, "user A's account must survive user B's chat attempt"
