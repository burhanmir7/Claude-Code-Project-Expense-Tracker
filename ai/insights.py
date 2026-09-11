import calendar
from datetime import date

from database.queries import get_budgets, get_category_breakdown


def get_insights(user_id, date_from=None, date_to=None):
    return {
        "top_category": _top_category_insight(user_id, date_from, date_to),
        "budget_headroom": _budget_headroom_insight(user_id),
    }


def _top_category_insight(user_id, date_from, date_to):
    breakdown = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)
    if len(breakdown) < 2:
        return None
    top = breakdown[0]
    return {"name": top["name"], "amount": top["amount"], "pct": top["pct"], "count": top["count"]}


def _budget_headroom_insight(user_id):
    budgets = get_budgets(user_id)
    if not budgets:
        return None

    ceiling_total = sum(b["monthly_ceiling"] for b in budgets)
    spent_total = sum(b["spent"] for b in budgets)
    headroom = ceiling_total - spent_total

    today = date.today()
    days_elapsed = today.day
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    projected_total = (spent_total / days_elapsed) * days_in_month if days_elapsed else spent_total

    return {
        "ceiling_total": ceiling_total,
        "spent_total": spent_total,
        "headroom": headroom,
        "projected_total": round(projected_total, 2),
        "budget_count": len(budgets),
    }
