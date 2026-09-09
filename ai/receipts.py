import base64
import json
from datetime import datetime

from ai import llm_client
from ai.prompts import RECEIPT_PROMPT
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


def extract_receipt(image_bytes, media_type, today):
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    reply = llm_client.create_message(
        system_text=RECEIPT_PROMPT,
        turns=[{"role": "user", "content": "Today is %s. Extract the receipt fields." % today.isoformat()}],
        image={"media_type": media_type, "data": b64},
        response_schema=RECEIPT_SCHEMA,
    )

    if reply.finish_reason == "refused":
        raise llm_client.AIUnavailableError("The assistant is temporarily unavailable. Please try again.")

    try:
        parsed = json.loads(reply.text)
    except (ValueError, TypeError):
        raise llm_client.AIUnavailableError("The assistant is temporarily unavailable. Please try again.")

    if not isinstance(parsed, dict):
        raise llm_client.AIUnavailableError("The assistant is temporarily unavailable. Please try again.")

    return parsed
