import base64
import logging
import os

from google import genai
from google.genai import errors, types

MODEL = "gemini-2.0-flash"
CHAT_MAX_TOKENS = 4096
EXTRACT_MAX_TOKENS = 1024
REQUEST_TIMEOUT_SECONDS = 30.0

logger = logging.getLogger(__name__)

_client = None


class AIError(Exception):
    status = 502

    def __init__(self, user_message):
        super().__init__(user_message)
        self.user_message = user_message


class AIConfigError(AIError):
    status = 503


class AIRateLimitError(AIError):
    status = 429


class AIUnavailableError(AIError):
    status = 502


class _ToolCall:
    def __init__(self, id, name, input):
        self.id = id
        self.name = name
        self.input = input


class _Reply:
    def __init__(self, text, tool_calls, finish_reason):
        self.text = text
        self.tool_calls = tool_calls
        self.finish_reason = finish_reason


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise AIConfigError("The AI assistant is not configured. Set LLM_API_KEY to enable it.")
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(REQUEST_TIMEOUT_SECONDS * 1000)),
        )
    return _client


def _build_contents(turns, image):
    contents = []
    for turn in turns:
        role = "model" if turn["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=turn["content"])]))

    if image is not None and contents:
        contents[-1].parts.append(
            types.Part.from_bytes(data=base64.b64decode(image["data"]), mime_type=image["media_type"])
        )

    return contents


def _build_tools(tools):
    if not tools:
        return None
    declarations = [
        types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters_json_schema=tool["input_schema"],
        )
        for tool in tools
    ]
    return [types.Tool(function_declarations=declarations)]


def _map_finish_reason(candidate, has_tool_calls):
    if has_tool_calls:
        return "tool_calls"
    reason = str(getattr(candidate, "finish_reason", "") or "")
    if reason == "MAX_TOKENS":
        return "length"
    if reason in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        return "refused"
    return "stop"


def create_message(system_text, context_text="", turns=None, tools=None, response_schema=None, image=None):
    client = get_client()
    turns = turns or []

    system_instruction = system_text
    if context_text:
        system_instruction = system_text + "\n\n" + context_text

    config_kwargs = {
        "system_instruction": system_instruction,
        "max_output_tokens": CHAT_MAX_TOKENS,
    }

    tool_config = _build_tools(tools)
    if tool_config:
        config_kwargs["tools"] = tool_config

    if response_schema:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_json_schema"] = response_schema

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=_build_contents(turns, image),
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except errors.APIError as exc:
        logger.warning("LLM request failed: %s", type(exc).__name__)
        if exc.code in (401, 403):
            raise AIConfigError("The AI assistant is not configured. Set LLM_API_KEY to enable it.") from exc
        if exc.code == 429:
            raise AIRateLimitError("The assistant is busy. Please try again in a moment.") from exc
        raise AIUnavailableError("The assistant is temporarily unavailable. Please try again.") from exc
    except Exception as exc:
        logger.warning("LLM request failed: %s", type(exc).__name__)
        raise AIUnavailableError("The assistant is temporarily unavailable. Please try again.") from exc

    raw_calls = response.function_calls or []
    tool_calls = [
        _ToolCall(id="call_%d" % i, name=call.name, input=dict(call.args or {}))
        for i, call in enumerate(raw_calls)
    ]

    candidate = response.candidates[0] if response.candidates else None
    finish_reason = _map_finish_reason(candidate, bool(tool_calls))

    try:
        text = response.text or ""
    except Exception:
        text = ""

    return _Reply(text=text, tool_calls=tool_calls, finish_reason=finish_reason)
