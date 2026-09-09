from datetime import date

from ai.receipts import RECEIPT_SCHEMA, detect_image_type, normalise_receipt


# ------------------------------------------------------------------ #
# detect_image_type                                                   #
# ------------------------------------------------------------------ #

def test_detect_image_type_png():
    assert detect_image_type(b"\x89PNG\r\n\x1a\n" + b"rest of file") == "image/png"


def test_detect_image_type_jpeg():
    assert detect_image_type(b"\xff\xd8\xff" + b"rest of file") == "image/jpeg"


def test_detect_image_type_webp():
    assert detect_image_type(b"RIFF" + b"1234" + b"WEBP" + b"rest of file") == "image/webp"


def test_detect_image_type_gif():
    assert detect_image_type(b"GIF89a" + b"rest of file") == "image/gif"


def test_detect_image_type_unsupported():
    assert detect_image_type(b"%PDF-1.4" + b"rest of file") is None


# ------------------------------------------------------------------ #
# normalise_receipt                                                    #
# ------------------------------------------------------------------ #

def test_normalise_receipt_valid_fields():
    fields = {"is_receipt": True, "amount": 249.5, "date": "2026-09-01", "description": "Lunch", "category": "Food"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert result == {"amount": "249.50", "date": "2026-09-01", "description": "Lunch", "category": "Food"}


def test_normalise_receipt_missing_amount_and_unparseable_date():
    fields = {"is_receipt": True, "amount": None, "date": "31/12/2026", "description": "x", "category": "Food"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert result["amount"] == ""
    assert result["date"] == "2026-09-01"


def test_normalise_receipt_truncates_long_description():
    fields = {"is_receipt": True, "amount": 10, "date": "2026-09-01", "description": "x" * 300, "category": "Food"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert len(result["description"]) == 200


def test_normalise_receipt_unknown_category_falls_back_to_other():
    fields = {"is_receipt": True, "amount": 10, "date": "2026-09-01", "description": "x", "category": "Groceries"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert result["category"] == "Other"


def test_normalise_receipt_non_positive_amount_becomes_blank():
    fields = {"is_receipt": True, "amount": 0, "date": "2026-09-01", "description": "x", "category": "Food"}

    result = normalise_receipt(fields, date(2026, 9, 1))

    assert result["amount"] == ""


# ------------------------------------------------------------------ #
# RECEIPT_SCHEMA                                                       #
# ------------------------------------------------------------------ #

def test_receipt_schema_category_enum_matches_categories():
    from database.db import CATEGORIES

    assert RECEIPT_SCHEMA["properties"]["category"]["enum"] == CATEGORIES
    assert RECEIPT_SCHEMA["additionalProperties"] is False
    assert set(RECEIPT_SCHEMA["required"]) == {"is_receipt", "amount", "date", "description", "category"}


import json

import pytest

from ai import llm_client
from ai.prompts import RECEIPT_PROMPT
from ai.receipts import RECEIPT_SCHEMA, extract_receipt
from tests.conftest import text_reply


# ------------------------------------------------------------------ #
# extract_receipt                                                     #
# ------------------------------------------------------------------ #

def test_extract_receipt_returns_parsed_json(fake_llm):
    payload = {"is_receipt": True, "amount": 249.5, "date": "2026-09-01", "description": "Lunch", "category": "Food"}
    fake_llm.responses.append(text_reply(json.dumps(payload)))

    result = extract_receipt(b"\x89PNG\r\n\x1a\n" + b"rest", "image/png", date(2026, 9, 1))

    assert result == payload
    call = fake_llm.calls[0]
    assert call["response_schema"] is RECEIPT_SCHEMA
    assert call["image"]["media_type"] == "image/png"
    assert call["system_text"] == RECEIPT_PROMPT
    assert "2026-09-01" in call["turns"][0]["content"]


def test_extract_receipt_raises_on_non_json_text(fake_llm):
    fake_llm.responses.append(text_reply("this is not json"))

    with pytest.raises(llm_client.AIUnavailableError):
        extract_receipt(b"\x89PNG\r\n\x1a\n", "image/png", date(2026, 9, 1))


def test_extract_receipt_raises_on_refused(fake_llm):
    fake_llm.responses.append(text_reply("", finish_reason="refused"))

    with pytest.raises(llm_client.AIUnavailableError):
        extract_receipt(b"\x89PNG\r\n\x1a\n", "image/png", date(2026, 9, 1))
