# FILE: memory.py
# Stores rolling conversation history for context-aware LLM responses.
# History is persisted to backend/data/conversation.json and restored on boot,
# so the 600s timeout no longer means total amnesia.
import json
import os
import time
from config import MEMORY_MAX_TURNS, MEMORY_TIMEOUT

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CONVERSATION_FILE = os.path.join(DATA_DIR, "conversation.json")


class Memory:
    def __init__(self):
        self.history = []
        self.last_time = 0.0
        self._restore()

    def _restore(self):
        try:
            if os.path.exists(CONVERSATION_FILE):
                with open(CONVERSATION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.history = list(data.get("history", []))
                    self.last_time = float(data.get("last_time", 0.0))
        except Exception:
            self.history = []

    def _persist(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(CONVERSATION_FILE, "w", encoding="utf-8") as f:
                json.dump({"history": self.history, "last_time": self.last_time}, f)
        except Exception:
            pass

    def add_user(self, text: str):
        self._check_timeout()
        self.history.append({"role": "user", "content": text})
        self._trim()
        self.last_time = time.time()
        self._persist()

    def add_assistant(self, text: str):
        self.history.append({"role": "assistant", "content": text})
        self._trim()
        self.last_time = time.time()
        self._persist()

    def get_messages(self) -> list:
        self._check_timeout()
        return list(self.history)

    def get_recent(self, n: int = 3) -> list:
        """Returns the last n (role, content) turns for context injection."""
        self._check_timeout()
        return list(self.history[-n:])

    def clear(self):
        self.history.clear()
        self._persist()

    def _check_timeout(self):
        if self.last_time and (time.time() - self.last_time > MEMORY_TIMEOUT):
            self.history.clear()

    def _trim(self):
        if len(self.history) > MEMORY_MAX_TURNS * 2:
            self.history = self.history[-(MEMORY_MAX_TURNS * 2):]
