import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import seed_db  # noqa: E402 (must follow sys.path insert above)


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)

    if "app" in sys.modules:
        app_module = importlib.reload(sys.modules["app"])
    else:
        app_module = importlib.import_module("app")

    seed_db()

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client


def register_new_user(client, name="New User", email="new@example.com", password="pass1234"):
    client.post(
        "/register",
        data={
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    client.post("/login", data={"email": email, "password": password})


def text_reply(text, finish_reason="stop"):
    return SimpleNamespace(text=text, tool_calls=[], finish_reason=finish_reason)


def tool_call_reply(name, tool_input, tool_id="call_01", text=None):
    call = SimpleNamespace(id=tool_id, name=name, input=tool_input)
    return SimpleNamespace(text=text or "", tool_calls=[call], finish_reason="tool_calls")


class FakeLLM:
    def __init__(self):
        self.responses = []
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr("ai.llm_client.create_message", fake)
    return fake
