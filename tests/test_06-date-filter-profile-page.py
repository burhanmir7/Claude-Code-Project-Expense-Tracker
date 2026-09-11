"""
Tests for Step 6: Date Filter for Profile Page.

Spec: .claude/specs/06-date-filter-profile-page.md

`GET /profile` gains two optional query params, `date_from` and `date_to`
(ISO `YYYY-MM-DD`, inclusive bounds). When both are present and valid
(date_from <= date_to) the three profile sections (summary stats, recent
transactions, category breakdown) are filtered to that range. When either
param is absent, malformed, or date_from > date_to, the route falls back to
the unfiltered "All Time" view. An invalid order (date_from > date_to) also
flashes "Start date must be before end date."; a malformed date does not.

The demo user (id=1) is reseeded fresh for every test via the `client`
fixture (see tests/conftest.py), always with 8 expenses summing to ₹318.24,
all dated within the current calendar month. For scenarios that need
precise control over expense dates (older-than-this-month, custom ranges,
zero-match ranges, etc.) a fresh user is registered and expenses are
inserted directly via parameterised SQL through `database.db.get_db()`.
"""

from datetime import date, timedelta

import pytest

from database.db import get_db, get_user_by_email
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)
from tests.conftest import register_new_user

DEMO_USER_ID = 1
DEMO_TOTAL = "₹318.24"
DEMO_TOP_CATEGORY = "Bills"

INVALID_ORDER_FLASH = "Start date must be before end date."


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def user_id_for(email):
    return get_user_by_email(email)["id"]


def insert_expense(user_id, amount, category, expense_date, description="Test expense"):
    """Insert a single expense row with an explicit date, bypassing seed_db."""
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
    client.post("/login", data={"email": "demo@wisex.com", "password": "demo123"})


@pytest.fixture
def ranged_expenses_user(client):
    """
    A fresh, logged-in user with 5 expenses spanning an 11-day window:
    two are deliberately outside the [today-10, today-6] window used by
    most of the range/limit/ordering tests below, three are inside it.

        today-11  Other      999.00  "out_before"   -> outside range
        today-10  Food         5.00  "e1"            -> range lower bound
        today-8   Transport    6.00  "e2"            -> inside range
        today-6   Bills        7.00  "e3"            -> range upper bound
        today-5   Health     888.00  "out_after"     -> outside range

    In-range total: 5.00 + 6.00 + 7.00 = 18.00 (3 transactions).
    Full total (no filter): 999 + 5 + 6 + 7 + 888 = 1905.00 (5 transactions).
    """
    today = date.today()
    email = "ranged@example.com"
    register_new_user(client, name="Ranged User", email=email, password="pass1234")
    uid = user_id_for(email)

    insert_expense(uid, 999.00, "Other", today - timedelta(days=11), "out_before")
    insert_expense(uid, 5.00, "Food", today - timedelta(days=10), "e1")
    insert_expense(uid, 6.00, "Transport", today - timedelta(days=8), "e2")
    insert_expense(uid, 7.00, "Bills", today - timedelta(days=6), "e3")
    insert_expense(uid, 888.00, "Health", today - timedelta(days=5), "out_after")

    return uid


RANGE_FROM_OFFSET = 10  # today - 10 days
RANGE_TO_OFFSET = 6     # today - 6 days


def ranged_window():
    today = date.today()
    return (
        (today - timedelta(days=RANGE_FROM_OFFSET)).isoformat(),
        (today - timedelta(days=RANGE_TO_OFFSET)).isoformat(),
    )


# ------------------------------------------------------------------ #
# GET /profile — auth guard                                           #
# ------------------------------------------------------------------ #

def test_profile_unauthenticated_redirects_without_params(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_unauthenticated_redirects_with_filter_params(client):
    response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
    assert response.status_code == 302, "Auth guard must apply regardless of query params"
    assert "/login" in response.headers["Location"]


# ------------------------------------------------------------------ #
# GET /profile — no params: Step 5 behaviour preserved                #
# ------------------------------------------------------------------ #

def test_profile_no_params_returns_unfiltered_alltime_data(client):
    login_demo(client)
    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    stats = get_summary_stats(DEMO_USER_ID)
    assert f"₹{stats['total_spent']:,.2f}" == DEMO_TOTAL, "Unfiltered total must match the full seed data sum"
    assert DEMO_TOP_CATEGORY in body
    for category in ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]:
        assert category in body


def test_profile_alltime_includes_expenses_older_than_any_preset_window(client):
    """An unfiltered request must show data with no time-window ceiling at all,
    not just an implicit longest preset window."""
    today = date.today()
    email = "oldtimer@example.com"
    register_new_user(client, name="Old Timer", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Shopping", today - timedelta(days=400), "very old")
    insert_expense(uid, 10.00, "Food", today, "recent")

    response = client.get("/profile")

    assert response.status_code == 200
    stats = get_summary_stats(uid)
    assert stats["total_spent"] == 50.00, "All-time view must include the 400-day-old expense too"


# ------------------------------------------------------------------ #
# GET /profile — preset-equivalent ranges                             #
# ------------------------------------------------------------------ #

def test_this_month_preset_range_matches_seed_data_totals(client):
    """Per spec, 'This Month' -> first day of current month through today.
    All demo seed expenses are generated within the current month, so this
    preset-equivalent range must reproduce the unfiltered totals exactly."""
    login_demo(client)
    today = date.today()
    month_start = today.replace(day=1)

    response = client.get(f"/profile?date_from={month_start.isoformat()}&date_to={today.isoformat()}")

    assert response.status_code == 200
    stats = get_summary_stats(DEMO_USER_ID, date_from=month_start.isoformat(), date_to=today.isoformat())
    assert f"₹{stats['total_spent']:,.2f}" == DEMO_TOTAL


def test_this_month_preset_excludes_previous_month_expenses(client):
    today = date.today()
    month_start = today.replace(day=1)
    last_day_prev_month = month_start - timedelta(days=1)

    email = "thismonth@example.com"
    register_new_user(client, name="This Month", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 15.00, "Food", today, "this month expense")
    insert_expense(uid, 500.00, "Bills", last_day_prev_month, "previous month expense")

    response = client.get(f"/profile?date_from={month_start.isoformat()}&date_to={today.isoformat()}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹15.00" in body, "This-month total should only include the in-month expense"
    assert "₹500.00" not in body, "Previous-month expense must not be included in this-month total"


def test_last_3_months_preset_range_includes_and_excludes_correctly(client):
    today = date.today()
    email = "threemonths@example.com"
    register_new_user(client, name="Three Months", email=email, password="pass1234")
    uid = user_id_for(email)

    insert_expense(uid, 25.00, "Food", today - timedelta(days=30), "inside 3-month window")
    insert_expense(uid, 500.00, "Bills", today - timedelta(days=150), "outside 3-month window")

    date_from = (today - timedelta(days=90)).isoformat()
    response = client.get(f"/profile?date_from={date_from}&date_to={today.isoformat()}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹25.00" in body
    assert "₹500.00" not in body


def test_last_6_months_preset_range_includes_and_excludes_correctly(client):
    today = date.today()
    email = "sixmonths@example.com"
    register_new_user(client, name="Six Months", email=email, password="pass1234")
    uid = user_id_for(email)

    insert_expense(uid, 35.00, "Transport", today - timedelta(days=150), "inside 6-month window")
    insert_expense(uid, 700.00, "Health", today - timedelta(days=250), "outside 6-month window")

    date_from = (today - timedelta(days=182)).isoformat()
    response = client.get(f"/profile?date_from={date_from}&date_to={today.isoformat()}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹35.00" in body
    assert "₹700.00" not in body


# ------------------------------------------------------------------ #
# GET /profile — custom range, inclusive boundaries                   #
# ------------------------------------------------------------------ #

def test_custom_range_filters_inclusive_boundaries(client):
    today = date.today()
    email = "custom@example.com"
    register_new_user(client, name="Custom Range", email=email, password="pass1234")
    uid = user_id_for(email)

    insert_expense(uid, 999.00, "Food", today - timedelta(days=11), "before range")
    insert_expense(uid, 10.00, "Transport", today - timedelta(days=10), "on lower bound")
    insert_expense(uid, 20.00, "Bills", today - timedelta(days=7), "middle of range")
    insert_expense(uid, 30.00, "Health", today - timedelta(days=5), "on upper bound")
    insert_expense(uid, 888.00, "Shopping", today - timedelta(days=4), "after range")

    date_from = (today - timedelta(days=10)).isoformat()
    date_to = (today - timedelta(days=5)).isoformat()
    response = client.get(f"/profile?date_from={date_from}&date_to={date_to}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    stats = get_summary_stats(uid, date_from=date_from, date_to=date_to)
    assert stats["total_spent"] == 60.00, "Total should be 10 + 20 + 30 = 60.00, inclusive of both boundaries"
    assert "₹999.00" not in body
    assert "₹888.00" not in body


# ------------------------------------------------------------------ #
# GET /profile — validation errors                                    #
# ------------------------------------------------------------------ #

def test_invalid_order_falls_back_and_flashes_error(client):
    login_demo(client)
    today = date.today()
    date_from = today.isoformat()
    date_to = (today - timedelta(days=30)).isoformat()

    response = client.get(f"/profile?date_from={date_from}&date_to={date_to}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert INVALID_ORDER_FLASH in body, "date_from > date_to must flash the exact spec'd error message"
    stats = get_summary_stats(DEMO_USER_ID)
    assert f"₹{stats['total_spent']:,.2f}" == DEMO_TOTAL, "Invalid order must fall back to the unfiltered totals"


def test_malformed_date_from_falls_back_without_crash_or_flash(client):
    login_demo(client)
    response = client.get("/profile?date_from=not-a-date&date_to=2026-01-31")
    body = response.get_data(as_text=True)

    assert response.status_code == 200, "Malformed date must never crash the app"
    stats = get_summary_stats(DEMO_USER_ID)
    assert f"₹{stats['total_spent']:,.2f}" == DEMO_TOTAL, "Malformed date must fall back to unfiltered totals"
    assert INVALID_ORDER_FLASH not in body, "Malformed input is not an ordering error and must not flash it"


def test_malformed_date_to_falls_back_without_crash_or_flash(client):
    login_demo(client)
    response = client.get("/profile?date_from=2026-01-01&date_to=also-not-a-date")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    stats = get_summary_stats(DEMO_USER_ID)
    assert f"₹{stats['total_spent']:,.2f}" == DEMO_TOTAL
    assert INVALID_ORDER_FLASH not in body


def test_only_date_from_provided_falls_back_to_unfiltered(client):
    """Spec: filters are only applied 'when both are provided'."""
    login_demo(client)
    today = date.today()
    response = client.get(f"/profile?date_from={today.isoformat()}")

    assert response.status_code == 200
    stats = get_summary_stats(DEMO_USER_ID)
    assert f"₹{stats['total_spent']:,.2f}" == DEMO_TOTAL


def test_only_date_to_provided_falls_back_to_unfiltered(client):
    login_demo(client)
    today = date.today()
    response = client.get(f"/profile?date_to={today.isoformat()}")

    assert response.status_code == 200
    stats = get_summary_stats(DEMO_USER_ID)
    assert f"₹{stats['total_spent']:,.2f}" == DEMO_TOTAL


# ------------------------------------------------------------------ #
# GET /profile — zero-match range edge case                           #
# ------------------------------------------------------------------ #

def test_zero_match_range_shows_empty_state_no_errors(client):
    login_demo(client)
    today = date.today()
    date_from = (today + timedelta(days=100)).isoformat()
    date_to = (today + timedelta(days=110)).isoformat()

    response = client.get(f"/profile?date_from={date_from}&date_to={date_to}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹0.00" in body
    assert "Account Balance" in body, "Page must still render normally, not error out"

    stats = get_summary_stats(DEMO_USER_ID, date_from=date_from, date_to=date_to)
    assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}
    assert get_category_breakdown(DEMO_USER_ID, date_from=date_from, date_to=date_to) == []
    assert get_recent_transactions(DEMO_USER_ID, date_from=date_from, date_to=date_to) == []


# ------------------------------------------------------------------ #
# GET /profile — currency symbol always present                       #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "build_query",
    [
        lambda today: "",
        lambda today: f"?date_from={today.replace(day=1).isoformat()}&date_to={today.isoformat()}",
        lambda today: f"?date_from={(today - timedelta(days=10)).isoformat()}&date_to={(today - timedelta(days=5)).isoformat()}",
        lambda today: f"?date_from={(today + timedelta(days=100)).isoformat()}&date_to={(today + timedelta(days=110)).isoformat()}",
        lambda today: "?date_from=not-a-date",
        lambda today: f"?date_from={today.isoformat()}&date_to={(today - timedelta(days=30)).isoformat()}",
    ],
    ids=["none", "this_month", "custom_range", "zero_match", "malformed", "invalid_order"],
)
def test_currency_symbol_present_regardless_of_filter_state(client, build_query):
    login_demo(client)
    query = build_query(date.today())
    response = client.get(f"/profile{query}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹" in body, f"Currency symbol must be present for query state: {query!r}"


# ------------------------------------------------------------------ #
# get_summary_stats — date-range behaviour                            #
# ------------------------------------------------------------------ #

def test_get_summary_stats_no_date_args_matches_pre_filter_behaviour(client):
    """Backward compatibility: calling with no date args must behave exactly
    like the Step 5 implementation (unfiltered)."""
    stats = get_summary_stats(DEMO_USER_ID)
    assert stats["total_spent"] == 318.24
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_with_date_range_filters_correctly(client, ranged_expenses_user):
    date_from, date_to = ranged_window()
    stats = get_summary_stats(ranged_expenses_user, date_from=date_from, date_to=date_to)

    assert stats["total_spent"] == 18.00
    assert stats["transaction_count"] == 3
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_partial_date_args_behaves_as_unfiltered(client, ranged_expenses_user):
    date_from, _ = ranged_window()
    unfiltered = get_summary_stats(ranged_expenses_user)
    partial = get_summary_stats(ranged_expenses_user, date_from=date_from)

    assert partial == unfiltered
    assert partial["transaction_count"] == 5
    assert partial["total_spent"] == 1905.00


# ------------------------------------------------------------------ #
# get_recent_transactions — date-range behaviour                      #
# ------------------------------------------------------------------ #

def test_get_recent_transactions_with_date_range_filters_and_orders(client, ranged_expenses_user):
    date_from, date_to = ranged_window()
    transactions = get_recent_transactions(ranged_expenses_user, date_from=date_from, date_to=date_to)

    descriptions = [t["description"] for t in transactions]
    assert descriptions == ["e3", "e2", "e1"], "Must be filtered to range and ordered newest first"
    dates = [t["date"] for t in transactions]
    assert dates == sorted(dates, reverse=True)


def test_get_recent_transactions_respects_limit_within_date_range(client, ranged_expenses_user):
    date_from, date_to = ranged_window()
    transactions = get_recent_transactions(
        ranged_expenses_user, limit=2, date_from=date_from, date_to=date_to
    )

    assert len(transactions) == 2
    assert [t["description"] for t in transactions] == ["e3", "e2"]


def test_get_recent_transactions_partial_date_args_behaves_as_unfiltered(client, ranged_expenses_user):
    _, date_to = ranged_window()
    unfiltered = get_recent_transactions(ranged_expenses_user)
    partial = get_recent_transactions(ranged_expenses_user, date_to=date_to)

    assert len(partial) == 5
    assert partial == unfiltered


# ------------------------------------------------------------------ #
# GET /profile — transaction search (?q=)                             #
# ------------------------------------------------------------------ #

def test_search_matches_description_case_insensitive(client):
    email = "search1@example.com"
    register_new_user(client, name="Search One", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Grocery run")
    insert_expense(uid, 10.00, "Transport", date.today(), "Cab ride")

    rows = get_recent_transactions(uid, search="grocery")

    assert len(rows) == 1
    assert rows[0]["description"] == "Grocery run"


def test_search_matches_category(client):
    email = "search2@example.com"
    register_new_user(client, name="Search Two", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")
    insert_expense(uid, 10.00, "Transport", date.today(), "Cab ride")

    rows = get_recent_transactions(uid, search="Food")

    assert len(rows) == 1
    assert rows[0]["category"] == "Food"


def test_search_composes_with_date_range(client):
    today = date.today()
    email = "search3@example.com"
    register_new_user(client, name="Search Three", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", today - timedelta(days=40), "Old grocery run")
    insert_expense(uid, 10.00, "Food", today, "New grocery run")

    rows = get_recent_transactions(
        uid, search="grocery",
        date_from=(today - timedelta(days=5)).isoformat(),
        date_to=today.isoformat(),
    )

    assert len(rows) == 1
    assert rows[0]["description"] == "New grocery run"


def test_search_no_matches_returns_empty(client):
    email = "search4@example.com"
    register_new_user(client, name="Search Four", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")

    rows = get_recent_transactions(uid, search="zzzznomatch")

    assert rows == []


def test_search_absent_behaves_as_before(client):
    email = "search5@example.com"
    register_new_user(client, name="Search Five", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40.00, "Food", date.today(), "Lunch")

    rows = get_recent_transactions(uid)

    assert len(rows) == 1


def test_route_search_query_param_filters_table(client):
    login_demo(client)
    response = client.get("/profile?q=bills")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Electricity" in body
    assert "Groceries" not in body


# ------------------------------------------------------------------ #
# get_category_breakdown — date-range behaviour                       #
# ------------------------------------------------------------------ #

def test_get_category_breakdown_with_date_range_excludes_out_of_range_categories(client, ranged_expenses_user):
    date_from, date_to = ranged_window()
    breakdown = get_category_breakdown(ranged_expenses_user, date_from=date_from, date_to=date_to)

    names = {c["name"] for c in breakdown}
    assert names == {"Food", "Transport", "Bills"}
    assert "Other" not in names, "Out-of-range expense's category must be excluded"
    assert "Health" not in names, "Out-of-range expense's category must be excluded"
    assert sum(c["pct"] for c in breakdown) == 100
    amounts = [c["amount"] for c in breakdown]
    assert amounts == sorted(amounts, reverse=True)


def test_get_category_breakdown_partial_date_args_behaves_as_unfiltered(client, ranged_expenses_user):
    date_from, _ = ranged_window()
    unfiltered = get_category_breakdown(ranged_expenses_user)
    partial = get_category_breakdown(ranged_expenses_user, date_from=date_from)

    assert {c["name"] for c in partial} == {c["name"] for c in unfiltered}
    assert len(partial) == 5
    assert sum(c["pct"] for c in partial) == 100


def test_get_category_breakdown_zero_match_range_returns_empty_list(client, ranged_expenses_user):
    today = date.today()
    date_from = (today + timedelta(days=100)).isoformat()
    date_to = (today + timedelta(days=110)).isoformat()

    assert get_category_breakdown(ranged_expenses_user, date_from=date_from, date_to=date_to) == []
