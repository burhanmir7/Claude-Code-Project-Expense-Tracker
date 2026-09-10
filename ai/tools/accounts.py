from ai.chat import CONTEXT_PROVIDERS
from ai.tools.registry import register_tool
from database.db import ACCOUNT_TYPES
from database.queries import (
    delete_account_by_id,
    get_account_by_id,
    get_accounts,
    get_net_worth,
    insert_account,
    update_account,
)


def _validate_account_fields(name, account_type, balance):
    if not name or not account_type:
        return "Name and type are required."
    if len(name) > 60:
        return "Name must be 60 characters or fewer."
    if account_type not in ACCOUNT_TYPES:
        return "Please select a valid account type."
    if balance is None or balance < 0:
        return "Balance must be zero or greater."
    return None


@register_tool(
    {
        "name": "list_accounts",
        "description": "List the user's savings, debt, and investment accounts with their current balances.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    mutating=False,
)
def list_accounts(user_id, tool_input):
    return {"accounts": get_accounts(user_id), "net_worth": get_net_worth(user_id)}


@register_tool(
    {
        "name": "get_net_worth",
        "description": "Get the user's total assets, debts, and net worth across all accounts.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    mutating=False,
)
def get_net_worth_tool(user_id, tool_input):
    return get_net_worth(user_id)


@register_tool(
    {
        "name": "add_account",
        "description": "Add a new savings, debt, or investment account for the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": ACCOUNT_TYPES},
                "balance": {"type": "number"},
            },
            "required": ["name", "type", "balance"],
            "additionalProperties": False,
        },
    },
    mutating=True,
)
def add_account(user_id, tool_input):
    name = tool_input.get("name")
    account_type = tool_input.get("type")
    balance = tool_input.get("balance")

    error = _validate_account_fields(name, account_type, balance)
    if error:
        return {"error": error}

    account_id = insert_account(user_id, name, account_type, balance)

    return {"ok": True, "account": {"id": account_id, "name": name, "type": account_type, "balance": balance}}


@register_tool(
    {
        "name": "update_account_balance",
        "description": (
            "Update the current balance of one of the user's accounts. Confirm which account "
            "the user means (by name) before calling this if there is any ambiguity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer"},
                "balance": {"type": "number"},
            },
            "required": ["account_id", "balance"],
            "additionalProperties": False,
        },
    },
    mutating=True,
)
def update_account_balance(user_id, tool_input):
    account_id = tool_input.get("account_id")
    balance = tool_input.get("balance")

    existing = get_account_by_id(account_id, user_id)
    if existing is None:
        return {"error": "Account not found."}

    error = _validate_account_fields(existing["name"], existing["type"], balance)
    if error:
        return {"error": error}

    update_account(account_id, user_id, existing["name"], existing["type"], balance)

    return {"ok": True, "account": {"id": account_id, "name": existing["name"], "type": existing["type"], "balance": balance}}


@register_tool(
    {
        "name": "delete_account",
        "description": (
            "Permanently delete one of the user's accounts. Only call this after the user has "
            "explicitly confirmed, in their most recent message, that they want this specific "
            "account deleted. If they have not confirmed, restate the account (name, type, "
            "balance) and ask first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer"},
            },
            "required": ["account_id"],
            "additionalProperties": False,
        },
    },
    mutating=True,
)
def delete_account(user_id, tool_input):
    account_id = tool_input.get("account_id")
    rowcount = delete_account_by_id(account_id, user_id)

    if rowcount == 0:
        return {"error": "Account not found."}

    return {"ok": True}


def net_worth_context(user_id):
    net = get_net_worth(user_id)
    if net["account_count"] == 0:
        return None
    return (
        "Net worth snapshot: assets ₹%.2f, debts ₹%.2f, net worth ₹%.2f across %d accounts."
        % (net["assets"], net["debts"], net["net_worth"], net["account_count"])
    )


CONTEXT_PROVIDERS.append(net_worth_context)
