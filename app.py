import calendar
import math
import sqlite3
from datetime import date, datetime

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ai import llm_client
from ai.chat import HISTORY_LIMIT, run_chat_turn
from ai.receipts import MAX_RECEIPT_BYTES, detect_image_type, extract_receipt, normalise_receipt
from database.db import CATEGORIES, create_user, get_user_by_email, init_db, seed_db
from database.queries import (
    delete_chat_messages,
    delete_expense_by_id,
    get_category_breakdown,
    get_chat_messages,
    get_expense_by_id,
    get_monthly_totals,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    insert_chat_message,
    insert_expense,
    update_expense,
)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _months_ago(reference_date, months):
    # month_index counts months since year 0, Jan=0; // and % roll negative
    # values back across a year boundary (e.g. Jan - 3 -> Oct of prev. year).
    month_index = reference_date.month - 1 - months
    year = reference_date.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(reference_date.day, last_day))


def _match_preset(date_from, date_to, preset_ranges):
    if date_from is None and date_to is None:
        return "all_time"
    return next(
        (name for name, (f, t) in preset_ranges.items() if (date_from, date_to) == (f, t)),
        None,
    )


def _json_error(message, status):
    return jsonify({"error": message}), status


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        flash("All fields are required.", "error")
        return render_template("register.html", name=name, email=email), 400

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return render_template("register.html", name=name, email=email), 400

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        flash("An account with this email already exists.", "error")
        return render_template("register.html", name=name, email=email), 400

    flash("Account created successfully. Please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email) if email and password else None

    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.", "error")
        return render_template("login.html"), 400

    session["user_id"] = user["id"]
    flash(f"Welcome back, {user['name']}!", "success")
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    today = date.today()

    parsed_from = _parse_date(request.args.get("date_from"))
    parsed_to = _parse_date(request.args.get("date_to"))

    if parsed_from and parsed_to and parsed_from > parsed_to:
        flash("Start date must be before end date.", "error")
        parsed_from = parsed_to = None

    date_from = parsed_from.isoformat() if parsed_from else None
    date_to = parsed_to.isoformat() if parsed_to else None

    preset_ranges = {
        "this_month": (today.replace(day=1).isoformat(), today.isoformat()),
        "last_3_months": (_months_ago(today, 3).isoformat(), today.isoformat()),
        "last_6_months": (_months_ago(today, 6).isoformat(), today.isoformat()),
    }

    active_preset = _match_preset(date_from, date_to, preset_ranges)
    filter_note = "All Time" if active_preset == "all_time" else "Filtered"

    profile_user = get_user_by_id(user_id)
    stats_raw = get_summary_stats(user_id, date_from=date_from, date_to=date_to)

    initials = "".join(word[0] for word in profile_user["name"].split()[:2]).upper()
    user = {
        "name": profile_user["name"],
        "email": profile_user["email"],
        "initials": initials,
        "member_since": profile_user["member_since"],
    }

    stats = [
        {"label": "Total spent", "value": f"₹{stats_raw['total_spent']:,.2f}", "note": filter_note, "icon": "wallet"},
        {"label": "Transactions", "value": str(stats_raw["transaction_count"]), "note": filter_note, "icon": "swap"},
        {"label": "Top category", "value": stats_raw["top_category"], "note": "", "icon": "tag"},
    ]

    transactions = [
        {
            "id": t["id"],
            "date": t["date"],
            "description": t["description"],
            "category": t["category"],
            "amount": f"₹{t['amount']:,.2f}",
        }
        for t in get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    ]

    month_start = today.replace(day=1).isoformat()
    monthly_expenses_total = get_summary_stats(user_id, date_from=month_start, date_to=today.isoformat())["total_spent"]
    monthly_expenses = f"₹{monthly_expenses_total:,.2f}"
    monthly_totals = get_monthly_totals(user_id)
    category_breakdown = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)

    return render_template(
        "profile.html", user=user, stats=stats,
        transactions=transactions,
        selected_from=date_from, selected_to=date_to,
        active_preset=active_preset, preset_ranges=preset_ranges,
        monthly_expenses=monthly_expenses, monthly_totals=monthly_totals,
        category_breakdown=category_breakdown, hide_chrome=True,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    today = date.today().isoformat()

    if request.method == "GET":
        return render_template("add_expense.html", categories=CATEGORIES, today=today)

    amount = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_str = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    # Pre-validation raw strings, used to repopulate the form on error.
    form_values = {"amount": amount, "category": category, "date": date_str, "description": description}

    def rerender(message):
        flash(message, "error")
        return render_template("add_expense.html", categories=CATEGORIES, today=today, **form_values), 400

    if not amount or not category or not date_str:
        return rerender("Amount, category, and date are required.")

    try:
        amount_value = float(amount)
    except ValueError:
        return rerender("Amount must be a valid number.")

    if amount_value <= 0:
        return rerender("Amount must be greater than zero.")

    if category not in CATEGORIES:
        return rerender("Please select a valid category.")

    parsed_date = _parse_date(date_str)
    if not parsed_date:
        return rerender("Please enter a valid date.")

    if len(description) > 200:
        return rerender("Description must be 200 characters or fewer.")

    insert_expense(session["user_id"], amount_value, category, parsed_date.isoformat(), description or None)

    flash("Expense added successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    existing = get_expense_by_id(id, user_id)
    if existing is None:
        abort(404)

    if request.method == "GET":
        return render_template("edit_expense.html", categories=CATEGORIES, expense=existing)

    amount = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_str = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    form_values = {
        "id": id,
        "amount": amount,
        "category": category,
        "date": date_str,
        "description": description,
    }

    def rerender(message):
        flash(message, "error")
        return render_template("edit_expense.html", categories=CATEGORIES, expense=form_values), 400

    if not amount or not category or not date_str:
        return rerender("Amount, category, and date are required.")

    try:
        amount_value = float(amount)
    except ValueError:
        return rerender("Amount must be a valid number.")

    if amount_value <= 0:
        return rerender("Amount must be greater than zero.")

    if category not in CATEGORIES:
        return rerender("Please select a valid category.")

    parsed_date = _parse_date(date_str)
    if not parsed_date:
        return rerender("Please enter a valid date.")

    if len(description) > 200:
        return rerender("Description must be 200 characters or fewer.")

    update_expense(id, user_id, amount_value, category, parsed_date.isoformat(), description or None)

    flash("Expense updated successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    existing = get_expense_by_id(id, user_id)
    if existing is None:
        abort(404)

    delete_expense_by_id(id, user_id)

    flash("Expense deleted successfully.", "success")
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# AI routes                                                           #
# ------------------------------------------------------------------ #

CHAT_HISTORY_LIMIT = 50
CHAT_MESSAGE_MAX_LENGTH = 2000


@app.route("/api/chat/history", methods=["GET"])
def chat_history():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    messages = get_chat_messages(user_id, limit=CHAT_HISTORY_LIMIT)
    return jsonify({"messages": messages})


@app.route("/api/chat", methods=["POST"])
def chat_send():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _json_error("Message is required.", 400)

    message = body.get("message")
    if not isinstance(message, str):
        return _json_error("Message is required.", 400)
    text = message.strip()
    if not text:
        return _json_error("Message is required.", 400)
    if len(text) > CHAT_MESSAGE_MAX_LENGTH:
        return _json_error("Message must be 2000 characters or fewer.", 400)

    history = get_chat_messages(user_id, limit=HISTORY_LIMIT)
    user = get_user_by_id(user_id)

    try:
        result = run_chat_turn(user_id, history, text, user["name"], date.today())
    except llm_client.AIError as e:
        return _json_error(e.user_message, e.status)

    insert_chat_message(user_id, "user", text)
    insert_chat_message(user_id, "assistant", result["reply"])

    return jsonify({"reply": result["reply"]})


@app.route("/api/chat/history", methods=["DELETE"])
def chat_clear():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    cleared = delete_chat_messages(user_id)
    return jsonify({"cleared": cleared})


@app.route("/api/chat/receipt", methods=["POST"])
def chat_scan_receipt():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    today = date.today()

    file = request.files.get("receipt")
    if not file or not file.filename:
        return _json_error("Please choose a receipt image.", 400)

    data = file.read()
    if len(data) > MAX_RECEIPT_BYTES:
        return _json_error("Receipt image must be 5 MB or smaller.", 400)

    media_type = detect_image_type(data)
    if media_type is None:
        return _json_error("Please upload a PNG, JPEG, WebP or GIF image.", 400)

    try:
        result = extract_receipt(data, media_type, today)
    except llm_client.AIError as e:
        return _json_error(e.user_message, e.status)

    if not result.get("is_receipt"):
        return _json_error("That image doesn't look like a receipt.", 400)

    fields = normalise_receipt(result, today)
    reply = "I found a %s expense of ₹%s from %s. Want me to save it?" % (
        fields["category"], fields["amount"], fields["date"],
    )

    insert_chat_message(user_id, "user", "📎 " + file.filename)
    insert_chat_message(user_id, "assistant", reply)

    return jsonify({"reply": reply, "expense": fields})


@app.route("/api/expenses", methods=["POST"])
def api_add_expense():
    user_id = session.get("user_id")
    if not user_id:
        return _json_error("Authentication required.", 401)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _json_error("Amount, category, and date are required.", 400)

    amount = (body.get("amount") or "").strip() if isinstance(body.get("amount"), str) else ""
    category = (body.get("category") or "").strip() if isinstance(body.get("category"), str) else ""
    date_str = (body.get("date") or "").strip() if isinstance(body.get("date"), str) else ""
    description = (body.get("description") or "").strip() if isinstance(body.get("description"), str) else ""

    if not amount or not category or not date_str:
        return _json_error("Amount, category, and date are required.", 400)

    try:
        amount_value = float(amount)
    except ValueError:
        return _json_error("Amount must be a valid number.", 400)

    if not math.isfinite(amount_value) or amount_value <= 0:
        return _json_error("Amount must be greater than zero.", 400)

    if category not in CATEGORIES:
        return _json_error("Please select a valid category.", 400)

    parsed_date = _parse_date(date_str)
    if not parsed_date:
        return _json_error("Please enter a valid date.", 400)

    if len(description) > 200:
        return _json_error("Description must be 200 characters or fewer.", 400)

    insert_expense(user_id, amount_value, category, parsed_date.isoformat(), description or None)

    return jsonify({"success": True})


with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
