import json

_TOOLS = {}


def register_tool(definition, mutating=False):
    def decorator(handler):
        _TOOLS[definition["name"]] = {
            "definition": definition,
            "handler": handler,
            "mutating": mutating,
        }
        return handler

    return decorator


def get_tool_definitions():
    return [entry["definition"] for entry in _TOOLS.values()]


def is_mutating(name):
    entry = _TOOLS.get(name)
    if entry is None:
        return False
    return entry["mutating"]


def execute_tool(name, tool_input, user_id):
    entry = _TOOLS.get(name)
    if entry is None:
        return json.dumps({"error": "Unknown tool: %s" % name}), True

    try:
        result = entry["handler"](user_id, tool_input)
    except Exception as exc:
        return json.dumps({"error": str(exc)}), True

    is_error = isinstance(result, dict) and "error" in result
    return json.dumps(result), is_error
