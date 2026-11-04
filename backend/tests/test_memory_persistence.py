"""Tests that Memory correctly persists conversation history to disk and restores it on a fresh instance."""
import json

import pytest

from llm import memory as memory_module
from llm.memory import Memory


@pytest.fixture()
def mem(monkeypatch, tmp_path):
    """Provide a Memory instance backed by a temp file."""
    conv_file = str(tmp_path / "conversation.json")
    monkeypatch.setattr(memory_module, "CONVERSATION_FILE", conv_file)
    monkeypatch.setattr(memory_module, "DATA_DIR", str(tmp_path))
    return Memory(), conv_file


def test_memory_persists_user_turn(mem):
    m, conv_file = mem
    m.add_user("hello boss")
    data = json.loads(open(conv_file, encoding="utf-8").read())
    assert any(t["content"] == "hello boss" for t in data["history"])


def test_memory_persists_assistant_turn(mem):
    m, conv_file = mem
    m.add_user("ping")
    m.add_assistant("pong, boss.")
    data = json.loads(open(conv_file, encoding="utf-8").read())
    roles = [t["role"] for t in data["history"]]
    assert "user" in roles and "assistant" in roles


def test_fresh_memory_restores_history(monkeypatch, tmp_path):
    """A second Memory() instance must restore what the first one persisted."""
    conv_file = str(tmp_path / "conversation.json")
    monkeypatch.setattr(memory_module, "CONVERSATION_FILE", conv_file)
    monkeypatch.setattr(memory_module, "DATA_DIR", str(tmp_path))

    m1 = Memory()
    m1.add_user("remember this")
    m1.add_assistant("remembered, boss.")

    m2 = Memory()
    messages = m2.get_messages()
    contents = [msg["content"] for msg in messages]
    assert "remember this" in contents
    assert "remembered, boss." in contents


def test_memory_clear_removes_persistence(monkeypatch, tmp_path):
    conv_file = str(tmp_path / "conversation.json")
    monkeypatch.setattr(memory_module, "CONVERSATION_FILE", conv_file)
    monkeypatch.setattr(memory_module, "DATA_DIR", str(tmp_path))

    m = Memory()
    m.add_user("to be forgotten")
    m.clear()

    m2 = Memory()
    assert m2.get_messages() == []


def test_get_recent_returns_last_n(mem):
    m, _ = mem
    m.add_user("one")
    m.add_assistant("a")
    m.add_user("two")
    m.add_assistant("b")
    recent = m.get_recent(2)
    assert len(recent) == 2
    assert recent[-1]["content"] == "b"
