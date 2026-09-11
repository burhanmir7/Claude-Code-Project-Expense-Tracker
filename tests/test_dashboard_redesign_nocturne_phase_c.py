from datetime import date

from ai.insights import get_insights
from database.db import get_user_by_email
from database.queries import (
    contribute_to_goal,
    get_budgets,
    get_goals,
    insert_account,
    insert_expense,
    insert_goal,
    net_worth_series,
    upsert_budget,
)
from tests.conftest import register_new_user


def login_demo(client):
    client.get("/logout")
    client.post("/login", data={"email": "demo@wisex.com", "password": "demo123"})


def user_id_for(email):
    return get_user_by_email(email)["id"]


# ------------------------------------------------------------------ #
# database/queries.py — budgets                                       #
# ------------------------------------------------------------------ #

def test_get_budgets_includes_spent_this_month(client):
    email = "budget1@example.com"
    register_new_user(client, name="Budget One", email=email, password="pass1234")
    uid = user_id_for(email)
    upsert_budget(uid, "Food", 100)
    insert_expense(uid, 40, "Food", date.today().isoformat(), "Lunch")

    budgets = get_budgets(uid)

    assert len(budgets) == 1
    assert budgets[0]["category"] == "Food"
    assert budgets[0]["monthly_ceiling"] == 100
    assert budgets[0]["spent"] == 40


def test_upsert_budget_updates_existing_row_instead_of_duplicating(client):
    email = "budget2@example.com"
    register_new_user(client, name="Budget Two", email=email, password="pass1234")
    uid = user_id_for(email)

    upsert_budget(uid, "Food", 100)
    upsert_budget(uid, "Food", 150)

    food_budgets = [b for b in get_budgets(uid) if b["category"] == "Food"]
    assert len(food_budgets) == 1
    assert food_budgets[0]["monthly_ceiling"] == 150


# ------------------------------------------------------------------ #
# database/queries.py — goals                                         #
# ------------------------------------------------------------------ #

def test_get_goals_returns_inserted_goal(client):
    email = "goal1@example.com"
    register_new_user(client, name="Goal One", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_goal(uid, "Trip", 1000, 200)

    goals = get_goals(uid)

    assert len(goals) == 1
    assert goals[0]["name"] == "Trip"
    assert goals[0]["target"] == 1000
    assert goals[0]["saved"] == 200


def test_contribute_to_goal_caps_at_target(client):
    email = "goal2@example.com"
    register_new_user(client, name="Goal Two", email=email, password="pass1234")
    uid = user_id_for(email)
    goal_id = insert_goal(uid, "Trip", 1000, 200)

    result = contribute_to_goal(goal_id, uid, 5000)

    assert result["saved"] == 1000


# ------------------------------------------------------------------ #
# database/queries.py — net_worth_series                               #
# ------------------------------------------------------------------ #

def test_net_worth_series_all_zero_with_no_accounts(client):
    email = "networth1@example.com"
    register_new_user(client, name="Net Worth One", email=email, password="pass1234")
    uid = user_id_for(email)

    series = net_worth_series(uid, months=3)

    assert len(series) == 3
    assert all(point["net_worth"] == 0 for point in series)


def test_net_worth_series_steps_up_in_current_month(client):
    email = "networth2@example.com"
    register_new_user(client, name="Net Worth Two", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_account(uid, "Savings", "savings", 500)

    series = net_worth_series(uid, months=3)

    assert series[-1]["net_worth"] == 500
    assert all(point["net_worth"] == 0 for point in series[:-1])


# ------------------------------------------------------------------ #
# ai/insights.py — get_insights                                        #
# ------------------------------------------------------------------ #

def test_get_insights_top_category_none_with_one_category(client):
    email = "insight1@example.com"
    register_new_user(client, name="Insight One", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40, "Food", date.today().isoformat(), "Lunch")

    result = get_insights(uid, None, None)

    assert result["top_category"] is None


def test_get_insights_top_category_present_and_no_budget_headroom(client):
    email = "insight2@example.com"
    register_new_user(client, name="Insight Two", email=email, password="pass1234")
    uid = user_id_for(email)
    insert_expense(uid, 40, "Food", date.today().isoformat(), "Lunch")
    insert_expense(uid, 10, "Transport", date.today().isoformat(), "Cab")

    result = get_insights(uid, None, None)

    assert isinstance(result["top_category"], dict)
    assert result["budget_headroom"] is None


def test_get_insights_budget_headroom_matches_ceiling_minus_spent(client):
    email = "insight3@example.com"
    register_new_user(client, name="Insight Three", email=email, password="pass1234")
    uid = user_id_for(email)
    upsert_budget(uid, "Food", 100)
    insert_expense(uid, 40, "Food", date.today().isoformat(), "Lunch")

    result = get_insights(uid, None, None)

    assert result["budget_headroom"]["headroom"] == 60


# ------------------------------------------------------------------ #
# Route — POST /api/goals/<id>/contribute                              #
# ------------------------------------------------------------------ #

def test_contribute_to_goal_route_requires_login(client):
    response = client.post("/api/goals/1/contribute")

    assert response.status_code == 401
    assert "error" in response.get_json()


def test_contribute_to_goal_route_404_for_other_users_goal(client):
    other_email = "goalowner@example.com"
    register_new_user(client, name="Goal Owner", email=other_email, password="pass1234")
    other_id = user_id_for(other_email)
    goal_id = insert_goal(other_id, "Their Trip", 1000, 0)

    login_demo(client)
    response = client.post(f"/api/goals/{goal_id}/contribute")

    assert response.status_code == 404


def test_contribute_to_goal_route_adds_5000_for_owner(client):
    email = "goalowner2@example.com"
    register_new_user(client, name="Goal Owner Two", email=email, password="pass1234")
    uid = user_id_for(email)
    goal_id = insert_goal(uid, "Trip", 100000, 1000)

    response = client.post(f"/api/goals/{goal_id}/contribute")

    assert response.status_code == 200
    body = response.get_json()
    assert body["saved"] == 6000

    assert get_goals(uid)[0]["saved"] == 6000


def test_contribute_to_goal_route_caps_at_target_near_completion(client):
    email = "goalowner3@example.com"
    register_new_user(client, name="Goal Owner Three", email=email, password="pass1234")
    uid = user_id_for(email)
    goal_id = insert_goal(uid, "Trip", 10000, 8000)

    response = client.post(f"/api/goals/{goal_id}/contribute")

    assert response.status_code == 200
    assert response.get_json()["saved"] == 10000


# ------------------------------------------------------------------ #
# Route — GET /profile with seeded data                                #
# ------------------------------------------------------------------ #

def test_profile_page_shows_seeded_budgets_and_goal_for_demo_user(client):
    login_demo(client)

    response = client.get("/profile")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Kyoto trip" in body
    assert "No budgets set yet" not in body
