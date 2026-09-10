from datetime import date

from database.db import get_db, get_user_by_email
from database.queries import get_category_breakdown, get_recent_transactions, get_summary_stats
from tests.conftest import register_new_user

DEMO_USER_ID = 1


def user_id_for(email):
    return get_user_by_email(email)["id"]


def insert_expense(user_id, amount, category, expense_date, description="Test expense"):
    if hasattr(expense_date, "isoformat"):
        expense_date = expense_date.isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, expense_date, description),
    )
    conn.commit()
    conn.close()


def login_demo(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})


# ------------------------------------------------------------------ #
# database/queries.py — get_recent_transactions(category=...)         #
# ------------------------------------------------------------------ #

def test_get_recent_transactions_category_filters_to_that_category(client):
    email = "drill1@example.com"
    register_new_user(client, name="Drill One", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")
    insert_expense(uid, 10.00, "Transport", date.today(), "Cab ride")

    rows = get_recent_transactions(uid, category="Food")

    assert len(rows) == 1
    assert rows[0]["category"] == "Food"


def test_get_recent_transactions_category_composes_with_search(client):
    email = "drill2@example.com"
    register_new_user(client, name="Drill Two", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Grocery run")
    insert_expense(uid, 12.00, "Food", date.today(), "Cab ride")

    rows = get_recent_transactions(uid, category="Food", search="grocery")

    assert len(rows) == 1
    assert rows[0]["description"] == "Grocery run"


def test_get_recent_transactions_category_none_behaves_as_unfiltered(client):
    email = "drill3@example.com"
    register_new_user(client, name="Drill Three", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")
    insert_expense(uid, 10.00, "Transport", date.today(), "Cab ride")

    rows = get_recent_transactions(uid)

    assert len(rows) == 2


def test_get_recent_transactions_category_no_matches_returns_empty(client):
    email = "drill4@example.com"
    register_new_user(client, name="Drill Four", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")

    rows = get_recent_transactions(uid, category="Bills")

    assert rows == []


# ------------------------------------------------------------------ #
# GET /profile?category=...                                           #
# ------------------------------------------------------------------ #

def test_route_category_param_filters_ledger_rows(client):
    login_demo(client)
    response = client.get("/profile?category=Bills")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Electricity" in body
    assert "Groceries" not in body


def test_route_category_param_does_not_affect_summary_or_breakdown(client):
    """Resolved decision: category drill-down applies to the ledger only —
    the donut/insight/budget placeholders read date-range-only data."""
    login_demo(client)
    unfiltered_stats = get_summary_stats(DEMO_USER_ID)
    unfiltered_breakdown = get_category_breakdown(DEMO_USER_ID)

    response = client.get("/profile?category=Bills")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f"₹{unfiltered_stats['total_spent']:,.2f}" in body, (
        "The route must not have passed category into get_summary_stats"
    )
    for row in unfiltered_breakdown:
        assert row["name"] in body, (
            "The route must not have passed category into get_category_breakdown"
        )


def test_route_invalid_category_falls_back_to_unfiltered(client):
    login_demo(client)
    response = client.get("/profile?category=NotARealCategory")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Electricity" in body
    assert "Groceries" in body


def test_route_no_category_param_behaves_as_before(client):
    login_demo(client)
    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Electricity" in body
    assert "Groceries" in body
