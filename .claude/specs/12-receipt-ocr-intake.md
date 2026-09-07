# Spec: Receipt OCR Intake

## Overview
Step 12 lets a user photograph or drag-and-drop a receipt on the Add Expense
page and have the AI assistant's image understanding read it. The image is
validated (type by magic bytes, size at most 5 MB), base64-encoded in
memory, and sent through the same `ai.llm_client.create_message()` seam the
chat drawer uses, requesting structured JSON output that constrains
`category` to the seven Spendly categories; the image is discarded
immediately after the call returns. Nothing here names or assumes an LLM
provider — that choice was already made once, in Step 10, inside
`ai/llm_client.py`. The
extracted `{amount, date, description, category}` values are used to
re-render the Add Expense form pre-filled — using the exact
`value="{{ amount or '' }}"` idiom the form already has — so the user reviews
and confirms before anything is saved. There is no uploads folder, no new
table, and no persistence of images or extractions. The scan is a plain HTML
form post; drag-and-drop is a progressive enhancement that submits the same
form.

## Depends on
- Step 7: Add Expense (`add_expense.html` prefill idiom, validation rules,
  `CATEGORIES`)
- Step 10: AI Chat Interface (the `create_message` seam and its normalized
  reply, `AIError` mapping, `EXTRACT_MAX_TOKENS`, `fake_llm`)

## Routes
- `POST /expenses/scan` — accept `multipart/form-data` field `receipt`, run
  extraction, render the Add Expense form pre-filled — logged-in only
  (redirect to `/login` otherwise; this is an HTML flow, not JSON)

View function name: `scan_receipt`.

Responses:
- `200` — `add_expense.html` rendered with `amount`, `category`, `date`,
  `description` set and a success flash "Receipt read — please check the
  details before saving."
- `400` re-render with an error flash when: no file or empty filename
  ("Please choose a receipt image."); unsupported type ("Please upload a
  PNG, JPEG, WebP or GIF image."); larger than 5 MB ("Receipt image must be
  5 MB or smaller."); the model reports `is_receipt: false` ("That image
  doesn't look like a receipt.")
- `503` / `429` / `502` re-render with `AIError.user_message` flashed (same
  mapping as chat)

Trade-off: a JSON endpoint plus JS prefill would avoid a full page render,
but the HTML post works with JS disabled, reuses the 400 re-render
convention, and needs no new template.

## Database changes
No database changes.

## Templates
- **Modify**: `templates/add_expense.html`
  - Add `{% block head %}` linking
    `{{ url_for('static', filename='css/receipt.css') }}`
  - Above the existing form card, add a second `.auth-card.receipt-card`
    containing:
    `<form id="receipt-form" method="POST"
    action="{{ url_for('scan_receipt') }}" enctype="multipart/form-data">`
    with `<label class="receipt-dropzone" id="receipt-dropzone"
    for="receipt">Drop a receipt image here or click to choose</label>`,
    `<input type="file" id="receipt" name="receipt"
    accept="image/png,image/jpeg,image/webp,image/gif"
    class="receipt-input" required>`, `<span id="receipt-filename"
    class="receipt-filename"></span>`, and
    `<button type="submit" class="btn-submit receipt-submit">Scan
    receipt</button>`
  - Add `{% block scripts %}` loading
    `{{ url_for('static', filename='js/receipt.js') }}` — the first
    page-specific use of the `scripts` block
  - The existing expense form is untouched; prefill works because the route
    passes the same `amount`, `category`, `date`, `description` keyword
    arguments the validation path already uses

## Files to change
- `app.py`
  - Import `detect_image_type`, `extract_receipt`, `normalise_receipt`,
    `MAX_RECEIPT_BYTES` from `ai.receipts`; `AIError` is already imported
  - Add `scan_receipt` next to `add_expense`: auth guard → `file =
    request.files.get("receipt")` → `data = file.read()` → size check →
    `media_type = detect_image_type(data)` → `extract_receipt(data,
    media_type, today)` inside `try/except AIError` → `is_receipt` check →
    `fields = normalise_receipt(result, today)` → flash success →
    `render_template("add_expense.html", categories=CATEGORIES,
    today=today, **fields)`
  - Optionally set `app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024` as a
    safety net (Flask then returns 413 for larger bodies before the route
    runs)
- `ai/prompts.py` — add `RECEIPT_PROMPT`: the image is a purchase receipt;
  `amount` is the grand total actually paid; `date` must be ISO
  `YYYY-MM-DD` or `null` if unreadable; `description` is a short label of at
  most 200 characters such as "Grocery run at Big Bazaar"; `category` is the
  best fit among the seven; `is_receipt` is `false` when the image is not a
  receipt or bill
- `templates/add_expense.html` — as above

## Files to create
- `ai/receipts.py` (no Flask imports)
  - `ALLOWED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp",
    "image/gif"}`; `MAX_RECEIPT_BYTES = 5 * 1024 * 1024`
  - `detect_image_type(data) -> str | None` — magic-byte sniffing:
    `\x89PNG\r\n\x1a\n` → `image/png`; `\xff\xd8\xff` → `image/jpeg`;
    `GIF87a` / `GIF89a` → `image/gif`; `RIFF` at 0 and `WEBP` at 8 →
    `image/webp`; anything else → `None`. Do not use `imghdr` — it was
    removed from the standard library in Python 3.13 and the project venv is
    3.14
  - `RECEIPT_SCHEMA` — JSON schema `{"type": "object", "properties":
    {"is_receipt": boolean, "amount": number|null, "date": string|null,
    "description": string|null, "category": {"type": "string", "enum":
    CATEGORIES}}, "required": [all five], "additionalProperties": false}`
  - `extract_receipt(image_bytes, media_type, today) -> dict` — builds
    `base64.standard_b64encode(image_bytes).decode("ascii")` (no newlines)
    and calls `llm_client.create_message(system_text=RECEIPT_PROMPT,
    turns=[{"role": "user", "content": f"Today is {today}. Extract the
    receipt fields."}], image={"media_type": media_type, "data": b64},
    response_schema=RECEIPT_SCHEMA)`, then `json.loads(reply.text)`. Raises
    `AIUnavailableError` when the text is not valid JSON or
    `reply.finish_reason == "refused"`. How the image and
    `response_schema` map onto the chosen provider's actual vision and
    structured-output mechanics is entirely `ai/llm_client.py`'s concern —
    this function only ever sees the normalized reply
  - `normalise_receipt(fields, today) -> dict` — pure: `amount` `None` or
    ≤ 0 → `""`, else `f"{amount:.2f}"`; `date` `None` or not parseable with
    `strptime` → `today.isoformat()`; `description` `None` → `""`, stripped
    and cut to 200 characters; `category` not in `CATEGORIES` → `"Other"`.
    Returns `{"amount", "category", "date", "description"}` as strings
- `static/css/receipt.css` — class prefix `receipt-`; dashed `--border`
  dropzone with `--radius-md`; `.receipt-dropzone-active` uses
  `--accent-light` and `--accent`; the file input is visually hidden but
  focusable; tokens only
- `static/js/receipt.js` — ES5 IIFE, null-guarded; `dragover` / `dragleave`
  toggle `receipt-dropzone-active`; on `drop` set `input.files =
  e.dataTransfer.files` and `form.submit()`; on `change` show the filename
  and submit; on submit disable the button and set its text to "Reading
  receipt…"

## New dependencies
No new dependencies (stdlib `base64`, `json`, `datetime`).

## Rules for implementation
- Image bytes live only in the request object and local variables; they are
  never written to disk, never stored in the DB or session, never logged
- The media type is decided by `detect_image_type` alone; `file.mimetype`
  and the filename extension are not trusted
- Size is checked with `len(data)` after `file.read()`; anything over
  `MAX_RECEIPT_BYTES` is rejected with 400 before any API call
- Request structured JSON output via `response_schema=RECEIPT_SCHEMA` on
  `create_message`; parse the reply with `json.loads`; the category enum in
  the schema is built from `CATEGORIES`, never retyped. How that maps onto
  the chosen provider's own structured-output or JSON-mode mechanism is
  `ai/llm_client.py`'s concern, not this module's
- The base64 image string contains no newlines
- `RECEIPT_PROMPT` is a stable constant passed as `system_text`; "today"
  travels inside the one `turns` entry, never baked into the prompt itself
- `max_tokens = EXTRACT_MAX_TOKENS` for the extraction call
- The route never inserts an expense — it only renders the form; saving
  still goes through `POST /expenses/add` and its validation
- The prefilled amount is passed as a two-decimal string so
  `<input type="number">` renders it
- Unauthenticated requests redirect to `/login` (HTML flow)
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in
  `get_db()`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $

## Tests to write
File: `tests/test_receipt_ocr_intake.py`

Build tiny image byte strings in the test (a PNG signature followed by a few
bytes is enough for `detect_image_type`); the fake never decodes them. Upload
with `client.post("/expenses/scan", data={"receipt": (io.BytesIO(png),
"receipt.png")}, content_type="multipart/form-data")`.

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `detect_image_type` | bytes starting `\x89PNG\r\n\x1a\n` | `"image/png"` |
| `detect_image_type` | bytes starting `\xff\xd8\xff` | `"image/jpeg"` |
| `detect_image_type` | `b"RIFF" + 4 bytes + b"WEBP"` | `"image/webp"` |
| `detect_image_type` | `b"GIF89a..."` | `"image/gif"` |
| `detect_image_type` | `b"%PDF-1.4"` | `None` |
| `normalise_receipt` | `{amount: 249.5, date: "2026-09-01", description: "Lunch", category: "Food"}` | `{"amount": "249.50", "date": "2026-09-01", "description": "Lunch", "category": "Food"}` |
| `normalise_receipt` | `amount: None, date: "31/12/2026"` | amount `""`; date equals `today.isoformat()` |
| `normalise_receipt` | description of 300 characters | truncated to 200 |
| `normalise_receipt` | category `"Groceries"` | `"Other"` |
| `extract_receipt` (fake) | fake returns `text_reply('{...valid JSON...}')` | dict returned; `fake.calls[0]["response_schema"] is RECEIPT_SCHEMA`; `fake.calls[0]["image"]["media_type"]` equals the given media type; `fake.calls[0]["system_text"] == RECEIPT_PROMPT` |
| `extract_receipt` (fake) | fake returns non-JSON text | raises `AIUnavailableError` |
| `extract_receipt` (fake) | fake returns `finish_reason="refused"` | raises `AIUnavailableError` |

### Route tests
`POST /expenses/scan` — unauthenticated:
- Redirects to `/login` (302)

`POST /expenses/scan` — authenticated, valid PNG, fake returns receipt JSON
for ₹249.50 / 2026-09-01 / "Lunch" / Food:
- Returns 200; body contains `value="249.50"`, `value="2026-09-01"`,
  `Lunch`, and the Food option marked `selected`
- No expense row was created
- Body contains the success flash text

`POST /expenses/scan` — authenticated, no file field:
- Returns 400; body contains an error flash

`POST /expenses/scan` — authenticated, PDF bytes uploaded as `receipt.png`:
- Returns 400 with the unsupported-type message (magic bytes win over the
  filename); `fake.calls` is empty

`POST /expenses/scan` — authenticated, 5 MB + 1 byte:
- Returns 400 with the size message; `fake.calls` is empty

`POST /expenses/scan` — authenticated, fake returns `is_receipt: false`:
- Returns 400 with "doesn't look like a receipt"

`POST /expenses/scan` — authenticated, `LLM_API_KEY` unset, no fake:
- Returns 503; form re-rendered with the "not configured" flash

`GET /expenses/add` — authenticated:
- Body contains `id="receipt-form"` and `js/receipt.js`

## Definition of done
- [ ] The Add Expense page shows a "Scan receipt" dropzone above the form
- [ ] Dropping or choosing an image submits it and the form comes back pre-filled with amount, date, description and category
- [ ] Nothing is saved until the user clicks "Add Expense"
- [ ] A non-image file or an image over 5 MB produces a clear error and no API call
- [ ] Without `LLM_API_KEY` the scan shows the "not configured" message and manual entry still works
- [ ] No file is written anywhere in the project during a scan (`git status` stays clean)
- [ ] All tests in `tests/test_receipt_ocr_intake.py` pass without `LLM_API_KEY`
