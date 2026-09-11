# Spendly AI Roadmap — Steps 10–14

**Status: all five steps shipped and merged to `main`.** Checkboxes below are
kept checked as a historical record of what each step delivered; see
`ARCHITECTURE.md` for the current state of the AI layer.

Pipeline for every step:

```
/create-spec <N> <name>  →  implement  →  /test-feature <NN-slug>
    →  /code-review-feature <NN-slug>  →  /ship-feature
```

Specs live in `.claude/specs/`. The only new pip package across all five
steps is the SDK for whichever LLM provider is chosen when Step 10 is
implemented — no provider is named in these docs. The model is pinned once,
as `ai.llm_client.MODEL` — see Step 10 — and never restated as a literal
elsewhere. Tests never call the network and never import a provider SDK —
they use the `fake_llm` fixture added in Step 10.

## Dependency graph

```
10 ai-chat-interface
├── 11 nl-crud-agent
│   ├── 13 analytics-and-advisor
│   └── 14 wealth-management
└── 12 receipt-ocr-intake      (needs only 10; could run parallel to 11)
```

Recommended order: 10 → 11 → 12 → 13 → 14. Steps 13 and 14 both edit
`ai/tools/__init__.py`, `ai/prompts.py`, `templates/profile.html` and
`static/css/profile.css` — never work on them in parallel.

Before starting: commit or discard the pending change to
`.claude/commands/ship-feature.md` — `/create-spec` refuses to run on a dirty
tree.

## Step 10 — AI Chat Interface (`10-ai-chat-interface`)
- [x] `/create-spec 10 ai-chat-interface` (spec already written — the
      command should only create the branch; skip its spec-writing step)
- [x] Choose the LLM provider; add its SDK to `requirements.txt` (e.g. `<provider-sdk>==<version>`); `pip install -r requirements.txt`; record the choice in `CLAUDE.md`'s pip carve-out line
- [x] `database/db.py`: `chat_messages` DDL in `init_db()`
- [x] `database/queries.py`: `get_chat_messages`, `insert_chat_message`, `delete_chat_messages`
- [x] `ai/__init__.py`, `ai/llm_client.py` (MODEL, lazy client, `create_message` seam with its normalized reply, `AIError` tree)
- [x] `ai/prompts.py` (`CHAT_SYSTEM_PROMPT`), `ai/chat.py` (`build_messages`, `CONTEXT_PROVIDERS`, `build_turn_context`, `run_chat_turn`)
- [x] `app.py`: `_json_error`, `GET/DELETE /api/chat/history`, `POST /api/chat` under `# AI routes`
- [x] `templates/_chat_drawer.html`, `static/css/chat.css`, `static/js/chat.js`, conditional include in `base.html`
- [x] `tests/conftest.py`: `text_reply`, `tool_call_reply`, `FakeLLM`, `fake_llm`
- [x] Verify `python app.py` boots with `LLM_API_KEY` unset
- [x] `/test-feature 10-ai-chat-interface`
- [x] `/code-review-feature 10-ai-chat-interface`
- [x] `/ship-feature`
- [x] `CLAUDE.md`: flip the three `/api/chat*` rows from Stub to Implemented

## Step 11 — NL CRUD Agent (`11-nl-crud-agent`)
- [x] `/create-spec 11 nl-crud-agent`
- [x] `ai/tools/registry.py` (`register_tool`, `get_tool_definitions`, `is_mutating`, `execute_tool`)
- [x] `ai/tools/__init__.py`, `ai/tools/expenses.py` (`list_expenses`, `add_expense`, `update_expense`, `delete_expense`, `_validate_expense_fields`)
- [x] `ai/chat.py`: tool loop, `MAX_TOOL_ROUNDS = 8`, `tools_used`
- [x] `ai/prompts.py`: tool usage + delete-confirmation rules
- [x] `app.py`: `refresh` in `POST /api/chat` response; `static/js/chat.js`: reload on `refresh`
- [x] `/test-feature 11-nl-crud-agent`
- [x] `/code-review-feature 11-nl-crud-agent` (checklist: no `from ai.llm_client import create_message` anywhere)
- [x] `/ship-feature`

## Step 12 — Receipt OCR Intake (`12-receipt-ocr-intake`)
- [x] `/create-spec 12 receipt-ocr-intake`
- [x] `ai/receipts.py` (`detect_image_type`, `RECEIPT_SCHEMA`, `extract_receipt`, `normalise_receipt`)
- [x] `ai/prompts.py`: `RECEIPT_PROMPT`
- [x] `app.py`: `POST /expenses/scan`
- [x] `templates/add_expense.html`: dropzone card, `head` + `scripts` blocks
- [x] `static/css/receipt.css`, `static/js/receipt.js`
- [x] `/test-feature 12-receipt-ocr-intake`
- [x] `/code-review-feature 12-receipt-ocr-intake`
- [x] `/ship-feature`
- [x] `CLAUDE.md`: flip `POST /expenses/scan` to Implemented

## Step 13 — Analytics and Advisor (`13-analytics-and-advisor`)
- [x] `/create-spec 13 analytics-and-advisor`
- [x] `database/queries.py`: `get_window_total`, `get_daily_average`, `get_month_comparison`, `get_category_month_comparison`, `get_high_spend_transactions`
- [x] `ai/insights.py` (`build_budget_insights`)
- [x] `ai/tools/analytics.py` + import line in `ai/tools/__init__.py`
- [x] `ai/prompts.py`: `ADVISOR_RULES`
- [x] `app.py`: `insights=` on `/profile`; `templates/profile.html` insights card; `static/css/profile.css`
- [x] `/test-feature 13-analytics-and-advisor`
- [x] `/code-review-feature 13-analytics-and-advisor`
- [x] `/ship-feature`

## Step 14 — Wealth Management (`14-wealth-management`)
- [x] `/create-spec 14 wealth-management`
- [x] `database/db.py`: `ACCOUNT_TYPES`, `accounts` DDL
- [x] `database/queries.py`: `get_accounts`, `get_account_by_id`, `insert_account`, `update_account`, `delete_account_by_id`, `get_net_worth`
- [x] `app.py`: `/accounts` routes under `# Account routes`; net-worth tile on `/profile`
- [x] `templates/accounts.html`, `add_account.html`, `edit_account.html`; `static/css/accounts.css`
- [x] `templates/base.html` nav link; `templates/profile.html` tile + `bank` icon; `static/css/profile.css` 4-tile grid
- [x] `ai/tools/accounts.py` (+ `CONTEXT_PROVIDERS` hook) + import line; `ai/prompts.py` accounts paragraph
- [x] `/test-feature 14-wealth-management`
- [x] `/code-review-feature 14-wealth-management`
- [x] `/ship-feature`
- [x] `CLAUDE.md`: flip the four `/accounts*` rows to Implemented

## Done when
- [x] All five feature branches are merged to `main`
- [x] `pytest` is green with `LLM_API_KEY` unset
- [x] `CLAUDE.md` route table has no "Stub" rows left
- [x] A fresh clone with a valid key can: chat, add/edit/delete an expense by chat, scan a receipt, ask for budget advice, and manage accounts
