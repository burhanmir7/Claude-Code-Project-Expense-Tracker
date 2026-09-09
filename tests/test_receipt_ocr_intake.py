import io
import json
from datetime import date

import pytest

from ai import llm_client
from ai.prompts import RECEIPT_PROMPT
from ai.receipts import RECEIPT_SCHEMA, detect_image_type, extract_receipt, normalise_receipt
from database.queries import get_summary_stats
from tests.conftest import text_reply


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


def test_extract_receipt_raises_on_non_object_json_text(fake_llm):
    fake_llm.responses.append(text_reply("[1, 2, 3]"))

    with pytest.raises(llm_client.AIUnavailableError):
        extract_receipt(b"\x89PNG\r\n\x1a\n", "image/png", date(2026, 9, 1))


def test_extract_receipt_raises_on_refused(fake_llm):
    fake_llm.responses.append(text_reply("", finish_reason="refused"))

    with pytest.raises(llm_client.AIUnavailableError):
        extract_receipt(b"\x89PNG\r\n\x1a\n", "image/png", date(2026, 9, 1))


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32
PDF_BYTES = b"%PDF-1.4" + b"0" * 32


def _upload(client, data, filename="receipt.png"):
    return client.post(
        "/expenses/scan",
        data={"receipt": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


# ------------------------------------------------------------------ #
# POST /expenses/scan                                                  #
# ------------------------------------------------------------------ #

def test_scan_receipt_requires_auth(client):
    response = _upload(client, PNG_BYTES)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_scan_receipt_success(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    before_count = get_summary_stats(1)["transaction_count"]
    payload = {"is_receipt": True, "amount": 249.5, "date": "2026-09-01", "description": "Lunch", "category": "Food"}
    fake_llm.responses.append(text_reply(json.dumps(payload)))

    response = _upload(client, PNG_BYTES)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'value="249.50"' in body
    assert 'value="2026-09-01"' in body
    assert "Lunch" in body
    assert 'value="Food" selected>' in body
    assert "Receipt read" in body
    assert get_summary_stats(1)["transaction_count"] == before_count


def test_scan_receipt_no_file(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.post("/expenses/scan", data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    assert "Please choose a receipt image." in response.get_data(as_text=True)


def test_scan_receipt_wrong_type(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = _upload(client, PDF_BYTES, filename="receipt.png")

    assert response.status_code == 400
    assert "PNG, JPEG, WebP or GIF" in response.get_data(as_text=True)
    assert fake_llm.calls == []


def test_scan_receipt_too_large(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024 + 1)

    response = _upload(client, oversized)

    assert response.status_code == 400
    assert "5 MB or smaller" in response.get_data(as_text=True)
    assert fake_llm.calls == []


def test_scan_receipt_not_a_receipt(client, fake_llm):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    payload = {"is_receipt": False, "amount": None, "date": None, "description": None, "category": "Other"}
    fake_llm.responses.append(text_reply(json.dumps(payload)))

    response = _upload(client, PNG_BYTES)

    assert response.status_code == 400
    # Jinja autoescapes the apostrophe as &#39; by default — keep this escaped, not a literal apostrophe.
    assert "doesn&#39;t look like a receipt" in response.get_data(as_text=True)


def test_scan_receipt_no_api_key_configured(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm_client._client = None
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = _upload(client, PNG_BYTES)

    assert response.status_code == 503
    assert "not configured" in response.get_data(as_text=True)


# ------------------------------------------------------------------ #
# GET /expenses/add (UI)                                              #
# ------------------------------------------------------------------ #

def test_add_expense_page_includes_receipt_dropzone(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})

    response = client.get("/expenses/add")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="receipt-form"' in body
    assert 'id="receipt-dropzone"' in body
    assert "js/receipt.js" in body
