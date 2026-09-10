from datetime import date, datetime

from database.db import get_db


def _user_date_filter(user_id, date_from, date_to):
    where = "WHERE user_id = ?"
    params = [user_id]
    if date_from and date_to:
        where += " AND date BETWEEN ? AND ?"
        params += [date_from, date_to]
    return where, params


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return None

    member_since = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%B %Y")
    return {"name": row["name"], "email": row["email"], "member_since": member_since}


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    where, params = _user_date_filter(user_id, date_from, date_to)

    totals = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt FROM expenses {where}",
        params,
    ).fetchone()

    if totals["cnt"] == 0:
        conn.close()
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

    top = conn.execute(
        f"SELECT category FROM expenses {where} "
        "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
        params,
    ).fetchone()
    conn.close()

    return {
        "total_spent": totals["total"],
        "transaction_count": totals["cnt"],
        "top_category": top["category"],
    }


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    where, params = _user_date_filter(user_id, date_from, date_to)
    params.append(limit)

    rows = conn.execute(
        "SELECT id, date, description, category, amount FROM expenses "
        f"{where} ORDER BY date DESC, id DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()

    return [
        {"id": r["id"], "date": r["date"], "description": r["description"], "category": r["category"], "amount": r["amount"]}
        for r in rows
    ]


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    where, params = _user_date_filter(user_id, date_from, date_to)

    rows = conn.execute(
        "SELECT category AS name, SUM(amount) AS amount FROM expenses "
        f"{where} GROUP BY category ORDER BY amount DESC",
        params,
    ).fetchall()
    conn.close()

    if not rows:
        return []

    total = sum(r["amount"] for r in rows)
    breakdown = [
        {"name": r["name"], "amount": r["amount"], "pct": round(r["amount"] / total * 100)}
        for r in rows
    ]

    remainder = 100 - sum(item["pct"] for item in breakdown)
    largest = max(breakdown, key=lambda item: item["amount"])
    largest["pct"] += remainder

    return breakdown


def insert_expense(user_id, amount, category, expense_date, description):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_expense_by_id(expense_id, user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return {
        "id": row["id"],
        "amount": row["amount"],
        "category": row["category"],
        "date": row["date"],
        "description": row["description"],
    }


def update_expense(expense_id, user_id, amount, category, expense_date, description):
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? "
            "WHERE id = ? AND user_id = ?",
            (amount, category, expense_date, description, expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def delete_expense_by_id(expense_id, user_id):
    conn = get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_chat_messages(user_id, limit=None):
    conn = get_db()
    try:
        query = "SELECT id, role, content, created_at FROM chat_messages WHERE user_id = ? ORDER BY id DESC"
        params = [user_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    rows = list(reversed(rows))
    return [
        {"id": row["id"], "role": row["role"], "content": row["content"], "created_at": row["created_at"]}
        for row in rows
    ]


def insert_chat_message(user_id, role, content):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_chat_messages(user_id):
    conn = get_db()
    try:
        cursor = conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_accounts(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, type, balance, updated_at FROM accounts "
            "WHERE user_id = ? ORDER BY type, name",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    return [
        {"id": r["id"], "name": r["name"], "type": r["type"], "balance": r["balance"], "updated_at": r["updated_at"]}
        for r in rows
    ]


def get_account_by_id(account_id, user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, type, balance, updated_at FROM accounts "
            "WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return {"id": row["id"], "name": row["name"], "type": row["type"], "balance": row["balance"], "updated_at": row["updated_at"]}


def insert_account(user_id, name, account_type, balance):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO accounts (user_id, name, type, balance) VALUES (?, ?, ?, ?)",
            (user_id, name, account_type, balance),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_account(account_id, user_id, name, account_type, balance):
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE accounts SET name = ?, type = ?, balance = ?, updated_at = datetime('now') "
            "WHERE id = ? AND user_id = ?",
            (name, account_type, balance, account_id, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def delete_account_by_id(account_id, user_id):
    conn = get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_net_worth(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT "
            "COALESCE(SUM(CASE WHEN type != 'debt' THEN balance ELSE 0 END), 0) AS assets, "
            "COALESCE(SUM(CASE WHEN type = 'debt' THEN balance ELSE 0 END), 0) AS debts, "
            "COUNT(*) AS cnt "
            "FROM accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    assets = row["assets"]
    debts = row["debts"]
    return {
        "assets": assets,
        "debts": debts,
        "net_worth": assets - debts,
        "account_count": row["cnt"],
    }


def get_monthly_totals(user_id, months=6):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT strftime('%Y-%m', date) AS ym, SUM(amount) AS total "
            "FROM expenses WHERE user_id = ? GROUP BY ym",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    totals_by_month = {row["ym"]: row["total"] for row in rows}

    today = date.today()
    year, month = today.year, today.month
    buckets = []
    for _ in range(months):
        buckets.append("%04d-%02d" % (year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    buckets.reverse()

    return [{"month": ym, "total": totals_by_month.get(ym, 0)} for ym in buckets]
