from ai import llm_client
from ai.prompts import CHAT_SYSTEM_PROMPT

HISTORY_LIMIT = 20

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
    reply = llm_client.create_message(
        system_text=CHAT_SYSTEM_PROMPT,
        context_text=build_turn_context(user_id, user_name, today),
        turns=build_messages(history, user_text),
    )

    if reply.finish_reason == "refused":
        text = "I can't help with that request."
    elif reply.finish_reason == "length":
        text = (reply.text or "") + " …"
    elif not reply.text:
        text = "Done."
    else:
        text = reply.text

    return {"reply": text, "tools_used": []}
