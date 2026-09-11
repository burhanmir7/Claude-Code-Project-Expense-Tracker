import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "expense_tracker.db")

CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]
ACCOUNT_TYPES = ["savings", "debt", "investment"]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('savings', 'debt', 'investment')),
            balance REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL CHECK (category IN
                ('Food', 'Transport', 'Bills', 'Health', 'Entertainment', 'Shopping', 'Other')),
            monthly_ceiling REAL NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, category),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            target REAL NOT NULL,
            saved REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS net_worth_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            net_worth REAL NOT NULL,
            recorded_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, month),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()


def create_user(name, email, password):
    password_hash = generate_password_hash(password)
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_db()
    user = conn.execute(
        "SELECT id, name, email, password_hash FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return user


def seed_db():
    conn = get_db()
    existing = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    if existing:
        conn.close()
        return

    password_hash = generate_password_hash("demo123")
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", password_hash),
    )
    user_id = cursor.lastrowid

    today = date.today()
    month_start = today.replace(day=1)
    days_into_month = (today - month_start).days

    def day_in_month(offset):
        return (month_start + timedelta(days=min(offset, days_into_month))).isoformat()

    sample_expenses = [
        (user_id, 12.50, "Food", day_in_month(0), "Lunch"),
        (user_id, 45.00, "Transport", day_in_month(1), "Gas"),
        (user_id, 120.00, "Bills", day_in_month(2), "Electricity"),
        (user_id, 30.00, "Health", day_in_month(3), "Pharmacy"),
        (user_id, 18.75, "Entertainment", day_in_month(4), "Movie tickets"),
        (user_id, 60.00, "Shopping", day_in_month(5), "Clothes"),
        (user_id, 9.99, "Other", day_in_month(6), "Misc"),
        (user_id, 22.00, "Food", day_in_month(2), "Groceries"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        sample_expenses,
    )

    budget_rows = [
        (user_id, "Food", 8000),
        (user_id, "Transport", 6000),
        (user_id, "Bills", 7000),
        (user_id, "Shopping", 5000),
    ]
    conn.executemany(
        "INSERT INTO budgets (user_id, category, monthly_ceiling) VALUES (?, ?, ?)",
        budget_rows,
    )
    conn.execute(
        "INSERT INTO goals (user_id, name, target, saved) VALUES (?, ?, ?, ?)",
        (user_id, "Kyoto trip", 150000, 45000),
    )

    conn.commit()
    conn.close()
