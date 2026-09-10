from datetime import datetime

from ai.tools.registry import register_tool
from database.db import CATEGORIES
from database.queries import (
    delete_expense_by_id,
    get_expense_by_id,
    get_recent_transactions,
    insert_expense,
    update_expense,
)

MIN_DATE = "0000-01-01"
MAX_DATE = "9999-12-31"


def _validate_expense_fields(amount, category, date_str, description):
    if amount is None or amount <= 0:
        return "Amount must be greater than zero."

    if category not in CATEGORIES:
        return "Please select a valid category."

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError):
        return "Please enter a valid date."

    if description is not None and len(description) > 200:
        return "Description must be 200 characters or fewer."

    return None


@register_tool(
    {
        "name": "list_expenses",
        "description": (
            "Search the user's expenses. Call this first to find the id before editing or deleting."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD, or null."},
                "date_to": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD, or null."},
                "category": {"type": ["string", "null"], "enum": CATEGORIES + [None]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["date_from", "date_to", "category", "limit"],
            "additionalProperties": False,
        },
    },
    mutating=False,
)
def list_expenses(user_id, tool_input):
    date_from = tool_input.get("date_from") or MIN_DATE
    date_to = tool_input.get("date_to") or MAX_DATE
    limit = tool_input.get("limit") or 10

    expenses = get_recent_transactions(user_id, limit=limit, date_from=date_from, date_to=date_to)

    category = tool_input.get("category")
    if category:
        expenses = [e for e in expenses if e["category"] == category]

    return {"expenses": expenses}


@register_tool(
    {
        "name": "add_expense",
        "description": "Add a new expense for the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "category": {"type": "string", "enum": CATEGORIES},
                "date": {"type": "string", "description": "ISO date YYYY-MM-DD."},
                "description": {"type": ["string", "null"]},
            },
            "required": ["amount", "category", "date", "description"],
            "additionalProperties": False,
        },
    },
    mutating=True,
)
def add_expense(user_id, tool_input):
    amount = tool_input.get("amount")
    category = tool_input.get("category")
    date_str = tool_input.get("date")
    description = tool_input.get("description")

    error = _validate_expense_fields(amount, category, date_str, description)
    if error:
        return {"error": error}

    expense_id = insert_expense(user_id, amount, category, date_str, description)

    return {
        "ok": True,
        "expense": {
            "id": expense_id,
            "amount": amount,
            "category": category,
            "date": date_str,
            "description": description,
        },
    }


@register_tool(
    {
        "name": "update_expense",
        "description": (
            "Update an existing expense. Call list_expenses first to find its id. "
            "Fields left null keep their current value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expense_id": {"type": "integer"},
                "amount": {"type": ["number", "null"]},
                "category": {"type": ["string", "null"], "enum": CATEGORIES + [None]},
                "date": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD, or null."},
                "description": {"type": ["string", "null"]},
            },
            "required": ["expense_id", "amount", "category", "date", "description"],
            "additionalProperties": False,
        },
    },
    mutating=True,
)
def update_expense_tool(user_id, tool_input):
    expense_id = tool_input.get("expense_id")
    existing = get_expense_by_id(expense_id, user_id)
    if existing is None:
        return {"error": "Expense not found."}

    amount = tool_input.get("amount")
    amount = existing["amount"] if amount is None else amount
    category = tool_input.get("category") or existing["category"]
    date_str = tool_input.get("date") or existing["date"]
    description = tool_input.get("description")
    description = existing["description"] if description is None else description

    error = _validate_expense_fields(amount, category, date_str, description)
    if error:
        return {"error": error}

    update_expense(expense_id, user_id, amount, category, date_str, description)

    return {
        "ok": True,
        "expense": {
            "id": expense_id,
            "amount": amount,
            "category": category,
            "date": date_str,
            "description": description,
        },
    }


@register_tool(
    {
        "name": "delete_expense",
        "description": (
            "Permanently delete one expense. Only call this after the user has explicitly "
            "confirmed, in their most recent message, that they want this specific expense "
            "deleted. If they have not confirmed, describe the expense and ask first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expense_id": {"type": "integer"},
            },
            "required": ["expense_id"],
            "additionalProperties": False,
        },
    },
    mutating=True,
)
def delete_expense(user_id, tool_input):
    expense_id = tool_input.get("expense_id")
    rowcount = delete_expense_by_id(expense_id, user_id)

    if rowcount == 0:
        return {"error": "Expense not found."}

    return {"ok": True}
