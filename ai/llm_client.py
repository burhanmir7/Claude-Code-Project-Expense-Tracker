import json
import logging
import os

import groq

CHAT_MODEL = "openai/gpt-oss-120b"
EXTRACTION_MODEL = "qwen/qwen3.6-27b"
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
        _client = groq.Groq(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
    return _client


def _build_messages(system_instruction, turns, image):
    messages = [{"role": "system", "content": system_instruction}]
    turns = list(turns)

    for i, turn in enumerate(turns):
        if turn["role"] == "tool_result":
            messages.append({
                "role": "tool",
                "tool_call_id": turn["tool_call_id"],
                "content": turn["content"],
            })
            continue

        if turn["role"] == "assistant" and turn.get("tool_calls"):
            messages.append({
                "role": "assistant",
                "content": turn["content"] or None,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call["input"]),
                        },
                    }
                    for call in turn["tool_calls"]
                ],
            })
            continue

        role = "assistant" if turn["role"] == "assistant" else "user"
        if image is not None and i == len(turns) - 1 and role == "user":
            messages.append({
                "role": role,
                "content": [
                    {"type": "text", "text": turn["content"]},
                    {"type": "image_url", "image_url": {
                        "url": "data:%s;base64,%s" % (image["media_type"], image["data"]),
                    }},
                ],
            })
        else:
            messages.append({"role": role, "content": turn["content"]})

    return messages


def _build_tools(tools):
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]


def _build_response_format(response_schema):
    if not response_schema:
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "extraction",
            "schema": response_schema,
            "strict": True,
        },
    }


def _map_finish_reason(finish_reason, has_tool_calls):
    if has_tool_calls:
        return "tool_calls"
    if finish_reason == "length":
        return "length"
    if finish_reason == "content_filter":
        return "refused"
    return "stop"


def create_message(system_text, context_text="", turns=None, tools=None, response_schema=None, image=None):
    client = get_client()
    turns = turns or []

    system_instruction = system_text
    if context_text:
        system_instruction = system_text + "\n\n" + context_text

    model = EXTRACTION_MODEL if response_schema else CHAT_MODEL

    request_kwargs = {
        "model": model,
        "messages": _build_messages(system_instruction, turns, image),
        "max_completion_tokens": EXTRACT_MAX_TOKENS if response_schema else CHAT_MAX_TOKENS,
    }

    tool_config = _build_tools(tools)
    if tool_config:
        request_kwargs["tools"] = tool_config

    response_format = _build_response_format(response_schema)
    if response_format:
        request_kwargs["response_format"] = response_format

    try:
        response = client.chat.completions.create(**request_kwargs)
    except groq.APIStatusError as exc:
        logger.warning("LLM request failed: %s", type(exc).__name__)
        if exc.status_code in (401, 403):
            raise AIConfigError("The AI assistant is not configured. Set LLM_API_KEY to enable it.") from exc
        if exc.status_code == 429:
            raise AIRateLimitError("The assistant is busy. Please try again in a moment.") from exc
        raise AIUnavailableError("The assistant is temporarily unavailable. Please try again.") from exc
    except Exception as exc:
        logger.warning("LLM request failed: %s", type(exc).__name__)
        raise AIUnavailableError("The assistant is temporarily unavailable. Please try again.") from exc

    message = response.choices[0].message

    raw_calls = message.tool_calls or []
    tool_calls = []
    for call in raw_calls:
        try:
            args = json.loads(call.function.arguments or "{}")
        except (ValueError, TypeError):
            args = {}
        tool_calls.append(_ToolCall(id=call.id, name=call.function.name, input=args))

    finish_reason = _map_finish_reason(response.choices[0].finish_reason, bool(tool_calls))
    text = message.content or ""

    return _Reply(text=text, tool_calls=tool_calls, finish_reason=finish_reason)
