from datetime import date

from database.queries import (
    get_category_breakdown,
    get_monthly_totals,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)
from tests.conftest import register_new_user

DEMO_USER_ID = 1


# ------------------------------------------------------------------ #
# get_user_by_id                                                      #
# ------------------------------------------------------------------ #

def test_get_user_by_id_valid(client):
    user = get_user_by_id(DEMO_USER_ID)
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    assert user["member_since"]


def test_get_user_by_id_missing(client):
    assert get_user_by_id(9999) is None


# ------------------------------------------------------------------ #
# get_summary_stats                                                   #
# ------------------------------------------------------------------ #

def test_get_summary_stats_with_expenses(client):
    stats = get_summary_stats(DEMO_USER_ID)
    assert stats["total_spent"] == 318.24
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_empty(client):
    register_new_user(client)
    stats = get_summary_stats(new_user_id_for(client))
    assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


# ------------------------------------------------------------------ #
# get_recent_transactions                                             #
# ------------------------------------------------------------------ #

def test_get_recent_transactions_ordered(client):
    transactions = get_recent_transactions(DEMO_USER_ID)
    assert len(transactions) == 8
    dates = [t["date"] for t in transactions]
    assert dates == sorted(dates, reverse=True)
    for t in transactions:
        assert set(t.keys()) == {"id", "date", "description", "category", "amount"}


def test_get_recent_transactions_empty(client):
    register_new_user(client)
    assert get_recent_transactions(new_user_id_for(client)) == []


# ------------------------------------------------------------------ #
# get_category_breakdown                                              #
# ------------------------------------------------------------------ #

def test_get_category_breakdown_full(client):
    breakdown = get_category_breakdown(DEMO_USER_ID)
    assert len(breakdown) == 7
    amounts = [c["amount"] for c in breakdown]
    assert amounts == sorted(amounts, reverse=True)
    assert sum(c["pct"] for c in breakdown) == 100


def test_get_category_breakdown_empty(client):
    register_new_user(client)
    assert get_category_breakdown(new_user_id_for(client)) == []


# ------------------------------------------------------------------ #
# Route tests                                                         #
# ------------------------------------------------------------------ #

def test_landing_unauthenticated_shows_landing_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Sign in" in response.get_data(as_text=True)


def test_landing_authenticated_redirects_to_profile(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.get("/")

    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]


def test_profile_unauthenticated_redirects(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_authenticated_seed_user(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹318.24" in body
    assert "Bills" in body
    for category in ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]:
        assert category in body


def test_profile_new_user_empty_state(client):
    register_new_user(client)
    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹0.00" in body


# ------------------------------------------------------------------ #
# get_monthly_totals                                                   #
# ------------------------------------------------------------------ #

def test_get_monthly_totals_returns_six_contiguous_months(client):
    from database.db import get_db

    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (1, 100.0, "Food", "2026-07-15", "test"),
    )
    conn.commit()
    conn.close()

    result = get_monthly_totals(1, months=6)

    assert len(result) == 6
    months = [row["month"] for row in result]
    assert months == sorted(months)
    for row in result:
        assert set(row.keys()) == {"month", "total"}


def test_get_monthly_totals_zero_fills_months_with_no_expenses(client):
    result = get_monthly_totals(999999, months=6)

    assert len(result) == 6
    assert all(row["total"] == 0 for row in result)


def test_get_monthly_totals_scoped_to_user(client):
    from database.db import get_db

    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (1, 500.0, "Food", date.today().isoformat(), "mine"),
    )
    conn.commit()
    conn.close()

    mine = get_monthly_totals(1, months=1)
    other = get_monthly_totals(999999, months=1)

    assert mine[0]["total"] >= 500.0
    assert other[0]["total"] == 0


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def new_user_id_for(client):
    from database.db import get_user_by_email

    return get_user_by_email("new@example.com")["id"]
