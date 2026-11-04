# FILE: brain.py
# Groq GPT-OSS 120B text routing, conversation, and coding with dedicated vision/search tools.
import json
import re
from logger import get_logger
from openai import AsyncOpenAI
from config import (
    GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3, GROQ_API_KEY_4, GROQ_API_KEY_5, GROQ_BASE_URL,
    ROUTER_MODEL, BRAIN_MODEL, CODER_MODEL,
    ROUTER_TEMPERATURE, ROUTER_MAX_TOKENS,
    BRAIN_TEMPERATURE, BRAIN_MAX_TOKENS,
    CODER_TEMPERATURE, CODER_MAX_TOKENS,
    DEV_MODE_DEFAULT,
)
from llm.prompts import ROUTER_PROMPT, BRAIN_PROMPT, CODER_PROMPT, ULTRON_PROMPT_SUFFIX
from llm.memory import Memory

_log = get_logger(__name__)
print = _log.info

CATEGORIES = {"chat", "code", "search", "vision", "direct_tool", "chain", "general_task"}

# Complex-project detection: requires a build/repair intent verb AND a project noun
# so plain actions like "open the YouTube website" don't get routed to the CodingAgent.
_COMPLEX_NOUNS = {
    "website", "site", "webapp", "store", "frontend", "backend", "platform",
    "dashboard", "portfolio", "app", "application", "project", "ecommerce",
    "ekart", "game", "bot", "server",
}
_COMPLEX_NOUN_PHRASES = ["web site", "web app", "e-commerce", "e commerce", "e-kart", "full stack", "fullstack"]
_BUILD_VERBS = {"make", "build", "create", "design", "implement", "develop", "deploy", "host", "generate", "clone", "set"}
_REPAIR_VERBS = {"fix", "solve", "resolve", "debug", "repair", "restart"}
_REPAIR_PHRASES = [
    "solve that error", "solve the error", "fix the error", "fix this error",
    "resolve the error", "resolve error", "solve error", "debug the project",
    "restart server", "restart the server",
]
# Signals that the user wants a small single-file script, not a scaffolded project.
_SIMPLE_SIGNALS = {
    "simple", "quick", "small", "script", "function", "single file", "one file",
    "calculator", "hello world", "fizzbuzz", "convert", "sort", "reverse",
    "print", "write a code", "write code", "write a python", "leetcode",
    "algorithm", "snippet", "question", "problem", "solution", "test script",
}


def detect_complex_project(task_desc: str, text: str) -> tuple:
    """Return (is_complex_project, is_repair) for a code-category task.

    Word-boundary matching avoids substring false positives (e.g. "restore"
    matching "store"). A bare noun alone is NOT enough — the LLM's
    task_description may rephrase a simple action as "Open the YouTube
    website", which must not become a coding project.
    """
    lower_combined = f"{task_desc} {text}".lower()
    words = set(re.findall(r"[a-z]+", lower_combined))
    is_repair = bool(words & _REPAIR_VERBS) or any(p in lower_combined for p in _REPAIR_PHRASES)
    # Explicit simple-task signals short-circuit to fast execute_code —
    # "make a simple calculator app" never needs a scaffolded project.
    if not is_repair and (words & _SIMPLE_SIGNALS or any(s in lower_combined for s in _SIMPLE_SIGNALS)):
        return False, False
    # Short coding requests without explicit full-stack/web targets stay as fast single-file code
    text_words = [w for w in re.findall(r"[a-z0-9]+", text.lower())]
    if not is_repair and len(text_words) < 15 and not any(k in lower_combined for k in ["website", "web app", "ecommerce", "e-commerce", "portfolio", "dashboard", "full stack", "fullstack"]):
        return False, False
    has_noun = bool(words & _COMPLEX_NOUNS) or any(p in lower_combined for p in _COMPLEX_NOUN_PHRASES)
    has_intent_verb = bool(words & (_BUILD_VERBS | _REPAIR_VERBS)) or is_repair
    return (has_noun and has_intent_verb) or any(p in lower_combined for p in _REPAIR_PHRASES), is_repair


class Brain:
    def __init__(self):
        # Initialize 5-Key Groq clients for dedicated routing, coding, and continuous failover
        self.client_1 = AsyncOpenAI(api_key=GROQ_API_KEY_1, base_url=GROQ_BASE_URL)
        self.client_2 = AsyncOpenAI(api_key=GROQ_API_KEY_2, base_url=GROQ_BASE_URL)
        self.client_3 = AsyncOpenAI(api_key=GROQ_API_KEY_3, base_url=GROQ_BASE_URL)
        self.client_4 = AsyncOpenAI(api_key=GROQ_API_KEY_4, base_url=GROQ_BASE_URL)
        self.client_5 = AsyncOpenAI(api_key=GROQ_API_KEY_5, base_url=GROQ_BASE_URL)
        self.memory = Memory()
        self.persona = "jarvis"
        self.dev_mode = DEV_MODE_DEFAULT
        self.system_prompt = self._compose_system_prompt()
        self.brain_prompt = self._compose_brain_prompt()
        self._rate_limits = {}  # {key_name: cooldown_until_timestamp}

    def _router_clients(self):
        # Order: Primary Key 1 -> Failover Key 3 -> Failover Key 4 -> Failover Key 5 -> Failover Key 2
        import time
        now = time.time()
        order = [
            (self.client_1, "Key 1"),
            (self.client_3, "Key 3"),
            (self.client_4, "Key 4"),
            (self.client_5, "Key 5"),
            (self.client_2, "Key 2"),
        ]
        active = [c for c in order if self._rate_limits.get(c[1], 0) < now]
        cooldown = [c for c in order if self._rate_limits.get(c[1], 0) >= now]
        return active + cooldown

    def _coder_clients(self):
        # Order: Primary Key 2 -> Failover Key 4 -> Failover Key 5 -> Failover Key 1 -> Failover Key 3
        import time
        now = time.time()
        order = [
            (self.client_2, "Key 2"),
            (self.client_4, "Key 4"),
            (self.client_5, "Key 5"),
            (self.client_1, "Key 1"),
            (self.client_3, "Key 3"),
        ]
        active = [c for c in order if self._rate_limits.get(c[1], 0) < now]
        cooldown = [c for c in order if self._rate_limits.get(c[1], 0) >= now]
        return active + cooldown


    def _compose_system_prompt(self) -> str:
        """Fills the {tool_definitions} placeholder from the single source of truth."""
        from llm.tools import get_definitions_text
        prompt = ROUTER_PROMPT
        if "{tool_definitions}" in prompt:
            prompt = prompt.replace("{tool_definitions}", get_definitions_text(dev_mode=self.dev_mode))
        if self.persona == "ultron":
            prompt += ULTRON_PROMPT_SUFFIX
        return prompt

    def _compose_brain_prompt(self) -> str:
        """Conversational brain prompt: persona + context block, no tool table."""
        prompt = BRAIN_PROMPT
        if self.persona == "ultron":
            prompt += ULTRON_PROMPT_SUFFIX
        return prompt

    def set_persona(self, persona: str) -> None:
        self.persona = persona
        self.system_prompt = self._compose_system_prompt()
        self.brain_prompt = self._compose_brain_prompt()

    def set_dev_mode(self, enabled: bool) -> None:
        """Toggles between normal fast mode (core tools only) and developer mode (full tools)."""
        self.dev_mode = bool(enabled)
        self.system_prompt = self._compose_system_prompt()
        print(f"[Brain] Dev mode {'enabled' if self.dev_mode else 'disabled'}. System prompt recomposed.")

    def _needs_deep_conversation(self, text: str) -> bool:
        """Determine if a chat request needs a separate conversational reasoning pass
        instead of relying directly on the router's immediate reply."""
        words = text.strip().split()
        if len(words) > 22:
            return True
        lower = text.lower()
        depth_markers = [
            "why ", "why?", "explain", "how does", "tell me about", "what do you think",
            "describe", "elaborate", "in detail", "difference between", "compare",
            "philosophy", "teach me", "what is the meaning of"
        ]
        return any(marker in lower for marker in depth_markers)

    def _build_context_block(self, text: str) -> str:
        """Builds a [CONTEXT] block injected into the router prompt so Jarvis knows
        who the user is, what they're looking at, and what it remembers."""
        parts = []
        try:
            from user_profile import all as profile_all
            profile = profile_all()
            parts.append(f"User: {profile.get('name', 'User')}")
            parts.append(f"City: {profile.get('city', 'London')}")
        except Exception:
            pass
        try:
            from datetime import datetime
            parts.append(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        except Exception:
            pass
        try:
            from tools.context import get_context_summary
            ctx = get_context_summary()
            if ctx:
                parts.append(ctx)
        except Exception:
            pass
        try:
            from tools.persistent_memory import recall_relevant
            mems = recall_relevant(text, top_n=3)
            if mems:
                parts.append("Relevant memories: " + "; ".join(mems))
        except Exception:
            pass
        try:
            recent = self.memory.get_recent(n=3)
            if recent:
                recent_text = " | ".join(f"{m['role']}: {m['content']}" for m in recent)
                parts.append(f"Recent conversation: {recent_text}")
        except Exception:
            pass
        if not parts:
            return ""
        return "[CONTEXT]\n" + "\n".join(parts) + "\n[/CONTEXT]\n\n"

    async def think(self, text: str, lang: str = "en") -> dict:
        self.memory.add_user(text)
        classification = await self._route(text, lang=lang)
        category = classification.get("category", "chat")
        resp_display = classification.get("response") or "I had trouble processing that, boss."
        resp_tts = classification.get("response_tts") or resp_display

        if category == "chat":
            router_resp = classification.get("response", "").strip()
            # Fast path: If the router produced a solid natural response and user does
            # not require deep conversational analysis, use router response directly (1 API call).
            if router_resp and len(router_resp) >= 12 and not self._needs_deep_conversation(text):
                classification["response"] = router_resp
                classification["response_tts"] = classification.get("response_tts") or router_resp
                self.memory.add_assistant(classification["response"])
                return classification

            # Stage 2: The deep conversational brain writes the reply when requested.
            brain_resp = await self._converse(text, lang=lang)
            if brain_resp:
                classification["response"] = brain_resp.get("response") or brain_resp.get("response_tts") or ""
                classification["response_tts"] = brain_resp.get("response_tts") or classification["response"]
            else:
                classification["response"] = resp_display
                classification["response_tts"] = resp_tts
            self.memory.add_assistant(classification["response"])
            return classification

        elif category == "code":
            task_desc = classification.get("task_description", "").strip()
            fillers = {"so", "so,", "thank you", "thanks", "okay", "ok", "yes", "no", "hello", "hey", "in bhojpuri"}
            if not task_desc or len(task_desc) < 4 or task_desc.lower() in fillers or (text.lower().strip() in fillers and len(task_desc.split()) <= 2):
                classification["category"] = "chat"
                classification["tool"] = None
                classification["response"] = resp_display or "How can I help, boss?"
                classification["response_tts"] = resp_tts or classification["response"]
                self.memory.add_assistant(classification["response"])
                return classification

            # If NOT in dev_mode, all code tasks use fast execute_code (single-file code via gpt-oss-120b).
            # No heavy multi-step planning, no CodingAgent, keeping Jarvis fast and light for daily usage.
            if not self.dev_mode:
                code = await self._generate_code(task_desc)
                result = {
                    "tool": "execute_code",
                    "params": {"code": code},
                    "response": resp_display,
                    "response_tts": resp_tts,
                    "confirm": classification.get("confirm", False),
                }
                self.memory.add_assistant(resp_display)
                return result

            # When in dev_mode: Distinguish complex projects/repairs from small scripts/DSA questions
            is_complex, is_repair = detect_complex_project(task_desc, text)
            if is_complex:
                default_msg = "Diagnosing and resolving the issue in your project, boss." if is_repair else "Planning and developing project in VS Code, boss."
                print(f"[Brain] Complex coding project/repair detected in Dev Mode -> routing to CodingAgent")
                result = {
                    "tool": "coding_agent",
                    "params": {"task": task_desc or text, "original_prompt": text},
                    "response": resp_display or default_msg,
                    "response_tts": resp_tts or default_msg,
                    "confirm": False,
                }
                self.memory.add_assistant(result["response"])
                return result

            # In dev_mode for simple scripts, .bat files, DSA problems -> fast execute_code
            code = await self._generate_code(task_desc)
            result = {
                "tool": "execute_code",
                "params": {"code": code},
                "response": resp_display,
                "response_tts": resp_tts,
                "confirm": classification.get("confirm", False),
            }
            self.memory.add_assistant(resp_display)
            return result

        elif category == "chain":
            steps = classification.get("steps", [])
            steps_text = " ".join([s.get("task", s) if isinstance(s, dict) else str(s) for s in steps]).lower()
            # If the chain is building a project and hosting/checking ports on localhost, unify them into CodingAgent
            if any(k in steps_text for k in ["make a website", "build a website", "create a website", "e-commerce", "ecommerce", "project", "website"]) and any(p in steps_text for p in ["port", "localhost", "host", "run"]):
                print(f"[Brain] Unifying project build + localhost port chain into single CodingAgent task")
                unified_task = f"{text} (build the project and automatically host on an available localhost port)"
                result = {
                    "tool": "coding_agent",
                    "params": {"task": unified_task, "original_prompt": text},
                    "response": "Planning, building, and launching your project on an available localhost port, boss.",
                    "response_tts": "Planning, building, and launching your project on an available localhost port, boss.",
                    "confirm": False,
                }
                self.memory.add_assistant(result["response"])
                return result

            self.memory.add_assistant(resp_display)
            return {
                "tool": "execute_chain",
                "params": {"steps": steps},
                "response": resp_display,
                "response_tts": resp_tts,
                "confirm": False,
            }

        elif category == "general_task":
            task_desc = classification.get("task_description", "").strip() or text
            self.memory.add_assistant(resp_display)
            return {
                "tool": "execute_plan",
                "params": {"task": task_desc, "original_prompt": text},
                "response": resp_display or "Planning that out for you, boss.",
                "response_tts": resp_display or "Planning that out for you, boss.",
                "confirm": False,
            }

        elif category == "search":
            from tools.web_search import web_search
            try:
                raw_results = web_search({"query": text})
                if raw_results and not raw_results.startswith("No results") and not raw_results.startswith("Search error") and raw_results != "An error occurred, boss.":
                    summary_messages = [
                        {"role": "system", "content": "You are Jarvis, an AI desktop assistant. Using the search results provided, answer the user's question concisely in 1 to 2 clear sentences. Address the user as 'boss' (or omit honorific). Never mention URLs, links, or technical citations."},
                        {"role": "user", "content": f"Question: {text}\n\nSearch Results:\n{raw_results}"}
                    ]
                    answer = await self._chat_with_failover(
                        ROUTER_MODEL, summary_messages,
                        clients=self._router_clients(),
                        temperature=0.3, max_tokens=250, timeout=8
                    )
                    if answer and answer.strip():
                        answer_clean = answer.strip()
                        self.memory.add_assistant(answer_clean)
                        return {"tool": None, "params": {}, "response": answer_clean, "response_tts": answer_clean, "confirm": False}
            except Exception as e:
                print(f"[Brain] Search synthesis error: {e}")

            fallback_resp = "I searched for that, boss, but could not find a definitive answer."
            self.memory.add_assistant(fallback_resp)
            return {"tool": None, "params": {}, "response": fallback_resp, "response_tts": fallback_resp, "confirm": False}

        elif category == "vision":
            self.memory.add_assistant(resp_display)
            return {
                "tool": "screenshot",
                "params": {"analyze": True, "question": text},
                "response": "Let me take a look, boss.",
                "response_tts": "Let me take a look, boss.",
                "confirm": False,
            }

        elif category == "direct_tool":
            classification["response"] = resp_display
            classification["response_tts"] = resp_tts
            self.memory.add_assistant(resp_display)
            return classification

        self.memory.add_assistant("I had trouble processing that, boss.")
        return {"tool": None, "params": {}, "response": "I had trouble processing that, boss.", "response_tts": "I had trouble processing that, boss.", "confirm": False}

    async def _route(self, text: str, lang: str = "en") -> dict:
        history = self.memory.get_messages()
        sys_prompt = self._build_context_block(text) + self.system_prompt
        bhojpuri_markers = [
            "haal chaal", "ki haal", "ka haal", "kaise ba", "batawa", "tohar", "tohaar",
            "sakeni", "theek ba", "thik ba", "ka ho", "kaa ho", "bhojpuri", "raua", "rauwa", "sewa"
        ]
        is_bho = (lang == "bho") or any(m in text.lower() for m in bhojpuri_markers)
        if is_bho:
            sys_prompt += "\n\nCRITICAL CONTEXT: The user is speaking BHOJPURI. You MUST reply in authentic Bhojpuri channeling Indian actor RAVI KISHAN's charismatic, earthy swagger and lively cadence! (e.g. 'Sab theek ba boss! Tu batawa, kaise madad kar sakeni tohar?'). Return ONLY a JSON object with 'response' (romanized Bhojpuri) and 'response_tts' (Devanagari Bhojpuri script)."
        elif lang == "hi":
            sys_prompt += "\n\nCRITICAL CONTEXT: The user is speaking HINDI. You MUST reply in Hindi! You must return ONLY a JSON object with 'response' (romanized Hindi) and 'response_tts' (Devanagari Hindi script)."

        if not history or history[-1].get("role") != "user" or history[-1].get("content") != text:
            messages = [
                {"role": "system", "content": sys_prompt},
                *history,
                {"role": "user", "content": text},
            ]
        else:
            messages = [
                {"role": "system", "content": sys_prompt},
                *history,
            ]
        parsed = None
        for attempt in range(2):
            content = await self._chat_with_failover(
                ROUTER_MODEL, messages,
                clients=self._router_clients(),
                temperature=ROUTER_TEMPERATURE, max_tokens=ROUTER_MAX_TOKENS,
            )
            parsed = self._parse_json(content)
            if isinstance(parsed, dict):
                break
            print(f"[Brain] Router returned unparseable output (attempt {attempt + 1}): {content!r}")
        if not isinstance(parsed, dict):
            parsed = {}
        parsed.setdefault("category", "chat")
        parsed.setdefault("tool", None)
        parsed.setdefault("params", {})
        parsed.setdefault("response", "")
        parsed.setdefault("response_tts", parsed.get("response", ""))
        parsed.setdefault("confirm", False)
        parsed.setdefault("task_description", "")
        if parsed["category"] not in CATEGORIES:
            parsed["category"] = "chat"
        return parsed

    async def _converse(self, text: str, lang: str = "en") -> dict | None:
        """Stage 2 chat: the conversational brain (llama-3.3-70b) writes the actual
        reply with full history + context. Returns {'response', 'response_tts'} or None."""
        history = self.memory.get_messages()
        sys_prompt = self._build_context_block(text) + self.brain_prompt
        if lang == "bho":
            sys_prompt += "\n\nCRITICAL CONTEXT: The user is speaking BHOJPURI. Reply in authentic Bhojpuri."
        elif lang == "hi":
            sys_prompt += "\n\nCRITICAL CONTEXT: The user is speaking HINDI. Reply in Hindi."

        if not history or history[-1].get("role") != "user" or history[-1].get("content") != text:
            messages = [
                {"role": "system", "content": sys_prompt},
                *history,
                {"role": "user", "content": text},
            ]
        else:
            messages = [
                {"role": "system", "content": sys_prompt},
                *history,
            ]
        for attempt in range(2):
            content = await self._chat_with_failover(
                BRAIN_MODEL, messages,
                clients=self._router_clients(),
                temperature=BRAIN_TEMPERATURE, max_tokens=BRAIN_MAX_TOKENS,
            )
            parsed = self._parse_json(content)
            if isinstance(parsed, dict) and (parsed.get("response") or parsed.get("response_tts")):
                return parsed
            # Plain-text reply (model ignored JSON): accept as-is for display+TTS.
            if isinstance(content, str) and content.strip():
                clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                if clean:
                    return {"response": clean, "response_tts": clean}
            print(f"[Brain] Conversational brain returned unparseable output (attempt {attempt + 1})")
        return None

    async def _generate_code(self, task_description: str) -> str:
        messages = [
            {"role": "system", "content": CODER_PROMPT},
            {"role": "user", "content": f"Task: {task_description}\n\nWrite the Python script."},
        ]
        content = await self._chat_with_failover(
            CODER_MODEL, messages,
            clients=self._coder_clients(),
            temperature=CODER_TEMPERATURE, max_tokens=CODER_MAX_TOKENS,
        )
        return self._clean_code(content)

    async def _chat_with_failover(
        self,
        model: str,
        messages: list,
        clients: list[tuple[AsyncOpenAI, str]],
        **kwargs,
    ) -> str:
        """Call clients in sequential order. Automatically retries next key on rate limit (429), timeout, or error.
        Every invocation resets to the primary key specified as the first element in clients."""
        import time
        def _err_summary(err):
            msg = str(err)
            if len(msg) > 150:
                return msg[:150] + "..."
            return msg

        # If model is Gemini (e.g. gemini-2.5-flash), execute with 7-key Gemini pool first
        if "gemini" in model.lower():
            try:
                from llm.gemini_client import gemini_client
                system_parts = [m["content"] for m in messages if m.get("role") == "system"]
                user_parts = [m["content"] for m in messages if m.get("role") != "system"]
                sys_ctx = "\n".join(system_parts)
                usr_ctx = "\n".join(user_parts)
                combined = f"{sys_ctx}\n\n{usr_ctx}" if sys_ctx else usr_ctx
                gem_text = gemini_client.generate_content_with_failover(combined, model=model)
                if gem_text and gem_text.strip():
                    return gem_text.strip()
            except Exception as e:
                print(f"[Brain] Gemini pool exception: {e}")
            print(f"[Brain] [FAILOVER] Shifting from {model} to Groq 120B fallback pool...")
            model = "openai/gpt-oss-120b"

        groq_kwargs = {k: v for k, v in kwargs.items() if k in ("temperature", "max_tokens", "timeout")}
        if "timeout" not in groq_kwargs:
            from config import ROUTER_TIMEOUT, CODER_TIMEOUT
            # Enforce a sane timeout for the router, a longer one for heavy coder
            groq_kwargs["timeout"] = ROUTER_TIMEOUT if ("20b" in model or model == ROUTER_MODEL) else CODER_TIMEOUT

        groq_messages = list(messages)

        for i, (client, name) in enumerate(clients):
            try:
                response = await client.chat.completions.create(
                    model=model, messages=groq_messages, **groq_kwargs
                )
                content = response.choices[0].message.content or ""
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                if content:
                    if i > 0:
                        print(f"[Brain] [OK] Failover ({name}) succeeded for {model}")
                    return content
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate limit" in err_str.lower():
                    # Place key in 60-second cooldown so subsequent requests don't lag
                    self._rate_limits[name] = time.time() + 60.0
                if "413" in err_str or "request too large" in err_str.lower():
                    # Per-organization size cap: every key hits the same wall, so
                    # stop cycling keys immediately instead of burning all five.
                    print(f"[Brain] {model} on {name}: request too large for service tier — stopping failover.")
                    return ""
                next_name = clients[i + 1][1] if i + 1 < len(clients) else "none"
                print(f"[Brain] {model} on {name} failed: {_err_summary(e)}")
                if next_name != "none":
                    print(f"[Brain] [FAILOVER] Automatically switching {model} to {next_name}...")

        return ""

    @staticmethod
    def _parse_json(content: str):
        if not content:
            return None

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
        if fence_match:
            content = fence_match.group(1).strip()

        # 1) Try direct parse
        try:
            return json.loads(content)
        except Exception:
            pass

        # 2) Extract the outermost { ... } block (greedy — handles nested braces)
        # Find the first '{' and the last '}'
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end > start:
            candidate = content[start:end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        # 3) Try all { ... } blocks from regex (non-greedy for smaller objects)
        for match in re.finditer(r"\{[^{}]*\}", content):
            try:
                return json.loads(match.group(0))
            except Exception:
                continue

        # 4) Fallback: if the model returned direct conversational text without JSON wrapper
        clean_text = content.strip().strip('"\'')
        if clean_text and not clean_text.startswith("<") and not clean_text.startswith("{") and "\n" not in clean_text:
            return {
                "category": "chat",
                "tool": None,
                "params": {},
                "response": clean_text,
                "response_tts": clean_text,
                "confirm": False
            }

        return None

    @staticmethod
    def _clean_code(content: str) -> str:
        if not content:
            return ""
        # Strip markdown code fences if the model wrapped output in them.
        match = re.search(r"```(?:python)?\s*(.*?)```", content, re.DOTALL)
        if match:
            code = match.group(1).strip()
        else:
            # Handle unclosed code fence
            match_unclosed = re.search(r"```(?:python)?\s*(.*)", content, re.DOTALL)
            code = match_unclosed.group(1).strip() if match_unclosed else content.strip()

        # Remove stray box-drawing tree diagram lines if any got included
        lines = [line for line in code.splitlines() if not any(c in line for c in ("\u2502", "\u251c", "\u2514", "\u2500"))]
        return "\n".join(lines).strip()
