from ai import llm_client
from ai.prompts import CHAT_SYSTEM_PROMPT
from ai.tools import execute_tool, get_tool_definitions

HISTORY_LIMIT = 20
MAX_TOOL_ROUNDS = 8

CONTEXT_PROVIDERS = []


def build_messages(history, user_text):
    trimmed = list(history[-HISTORY_LIMIT:])
    while trimmed and trimmed[0]["role"] == "assistant":
        trimmed = trimmed[1:]

    turns = [{"role": row["role"], "content": row["content"]} for row in trimmed]
    turns.append({"role": "user", "content": user_text})
    return turns


def build_turn_context(user_id, user_name, today):
    parts = ["Today is %s." % today.isoformat(), "The user's name is %s." % user_name]
    for provider in CONTEXT_PROVIDERS:
        result = provider(user_id)
        if result:
            parts.append(result)
    return " ".join(parts)


def run_chat_turn(user_id, history, user_text, user_name, today):
    turns = build_messages(history, user_text)
    context_text = build_turn_context(user_id, user_name, today)
    tools_used = []
    rounds = 0
    reply = None

    while True:
        reply = llm_client.create_message(
            system_text=CHAT_SYSTEM_PROMPT,
            context_text=context_text,
            turns=turns,
            tools=get_tool_definitions(),
        )

        if reply.finish_reason != "tool_calls" or rounds >= MAX_TOOL_ROUNDS:
            break

        turns.append({
            "role": "assistant",
            "content": reply.text,
            "tool_calls": [
                {"id": c.id, "name": c.name, "input": dict(c.input)} for c in reply.tool_calls
            ],
        })

        for call in reply.tool_calls:
            content_json, is_error = execute_tool(call.name, dict(call.input), user_id)
            turns.append({
                "role": "tool_result",
                "tool_call_id": call.id,
                "content": content_json,
                "is_error": is_error,
            })
            tools_used.append(call.name)

        rounds += 1

    if reply.finish_reason == "tool_calls" and rounds >= MAX_TOOL_ROUNDS:
        text = "I couldn't finish that request. Please try a simpler instruction."
    elif reply.finish_reason == "refused":
        text = "I can't help with that request."
    elif reply.finish_reason == "length":
        text = (reply.text or "") + " …"
    elif not reply.text:
        text = "Done."
    else:
        text = reply.text

    return {"reply": text, "tools_used": tools_used}
