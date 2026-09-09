from datetime import datetime

from database.db import CATEGORIES

ALLOWED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_RECEIPT_BYTES = 5 * 1024 * 1024

RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_receipt": {"type": "boolean"},
        "amount": {"type": ["number", "null"]},
        "date": {"type": ["string", "null"]},
        "description": {"type": ["string", "null"]},
        "category": {"type": "string", "enum": CATEGORIES},
    },
    "required": ["is_receipt", "amount", "date", "description", "category"],
    "additionalProperties": False,
}


def detect_image_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalise_receipt(fields, today):
    amount = fields.get("amount")
    if amount is None or amount <= 0:
        amount_str = ""
    else:
        amount_str = "%.2f" % amount

    date_str = fields.get("date")
    try:
        if date_str is None:
            raise ValueError("no date")
        datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        date_str = today.isoformat()

    description = fields.get("description")
    if description is None:
        description = ""
    description = description.strip()[:200]

    category = fields.get("category")
    if category not in CATEGORIES:
        category = "Other"

    return {
        "amount": amount_str,
        "category": category,
        "date": date_str,
        "description": description,
    }
