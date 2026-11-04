# FILE: backend/llm/planner.py
# Multi-step task planner: turns a general_task into an ordered list of tool steps,
# then executes them sequentially with result chaining, progress, and cancellation.

import json

from logger import get_logger

_log = get_logger(__name__)
print = _log.info

MAX_STEPS = 10


def _plan_prompt(task: str, tool_list: str, context: str) -> str:
    return f"""You are Jarvis's task planner. Break the user's goal into an ordered list of tool steps.

Available tools (JSON):
{tool_list}

Context:
{context}

User goal: {task}

Rules:
- Return ONLY a JSON array of steps: [{{"step": 1, "tool": "...", "params": {{...}}, "description": "..."}}, ...]
- Max {MAX_STEPS} steps.
- Each step may reference the output of a previous step as $result_N (N = step number).
- Use only tools from the available list. For anything not covered, use "run_shell_command" with a "command" param.
- Prefer the fewest steps that accomplish the goal safely.
"""


def parse_plan(content: str) -> list:
    """Parses the planner's JSON output, tolerating fences and prose."""
    if not content:
        return []
    # Strip markdown fences
    import re
    fence = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fence:
        content = fence.group(1).strip()
    # Find the outermost array
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end > start:
        candidate = content[start:end + 1]
        try:
            steps = json.loads(candidate)
            if isinstance(steps, list):
                return steps
        except Exception:
            pass
    return []


def resolve_results(steps: list, results: dict) -> list:
    """Replaces $result_N references in step params with prior step outputs."""
    resolved = []
    for step in steps:
        params = step.get("params", {})
        if isinstance(params, dict):
            new_params = {}
            for k, v in params.items():
                if isinstance(v, str) and v.startswith("$result_"):
                    idx = v[len("$result_"):]
                    try:
                        new_params[k] = results.get(int(idx), v)
                    except ValueError:
                        new_params[k] = v
                else:
                    new_params[k] = v
            step = {**step, "params": new_params}
        resolved.append(step)
    return resolved


class Planner:
    def __init__(self, brain):
        self.brain = brain

    async def create_plan(self, task: str, context: str, tool_list: str) -> list:
        """Plan tasks with Groq GPT-OSS 120B and the existing Groq key pool."""
        from config import CODING_AGENT_MODEL
        content = await self.brain._chat_with_failover(
            CODING_AGENT_MODEL,
            [{"role": "user", "content": _plan_prompt(task, tool_list, context)}],
            clients=self.brain._coder_clients(), temperature=0.2, max_tokens=2000,
        )
        return parse_plan(content)[:MAX_STEPS]


    async def execute(self, task: str, pipeline, lang: str = "en") -> str:
        """Creates a plan, speaks the plan review, and stores it as a pending action.
        Execution only happens after the user confirms — never runs steps optimistically."""
        from llm.tools import get_definitions_text
        context = ""
        try:
            context = self.brain._build_context_block(task)
        except Exception:
            pass
        tool_list = get_definitions_text()

        steps = await self.create_plan(task, context, tool_list)
        if not steps:
            return "I could not break that into steps, boss."

        # Plan review — speak the plan and ask for a single confirmation.
        summary = ", then ".join(s.get("description", s.get("tool", "step")) for s in steps)
        await pipeline.respond(f"I'll {summary}. That's {len(steps)} steps. Go ahead, boss?", lang=lang)

        # Store the plan as a pending action. The pipeline's confirmation gate
        # executes it on "yes" and discards it on "no". Nothing runs here.
        pipeline.pending_action = {
            "kind": "plan",
            "steps": steps,
            "task": task,
            "lang": lang,
        }
        return ""

    async def execute_steps(self, steps: list, pipeline, lang: str = "en") -> str:
        """Runs an already-confirmed plan sequentially with progress, result chaining,
        and per-step error handling."""
        from llm.tools import TOOL_HANDLERS
        from server.messages import plan_progress_msg

        total = len(steps)
        results = {}
        for step in steps:
            step_no = step.get("step", 0)
            tool = step.get("tool")
            params = step.get("params", {})

            # Resolve $result_N references from earlier steps.
            params = resolve_results([step], results)[0].get("params", params)

            # Allow the user to cancel mid-plan.
            if getattr(pipeline, "stop_event", None) and pipeline.stop_event.is_set():
                await pipeline.respond_and_idle("Plan cancelled, boss.", lang=lang)
                return "Plan cancelled, boss."

            pipeline.send(plan_progress_msg(step_no, total, "running"))

            handler = TOOL_HANDLERS.get(tool)
            if handler is None:
                results[step_no] = f"[unknown tool: {tool}]"
                pipeline.send(plan_progress_msg(step_no, total, "error"))
                continue
            try:
                # Plans are internally generated and must not invoke tools that
                # require a direct user utterance.
                from security.permissions import check_permission, PermissionResult
                decision = check_permission(tool, params, source="plan")
                if decision.result == PermissionResult.DENY:
                    results[step_no] = f"[denied: {decision.reason}]"
                    pipeline.send(plan_progress_msg(step_no, total, "error"))
                    continue
                tool_res = await pipeline._run_tool(tool, handler, params, source="plan")
                results[step_no] = tool_res
                pipeline.send(plan_progress_msg(step_no, total, "done"))
            except Exception as e:
                print(f"[Planner] Step {step_no} failed: {e}")
                results[step_no] = f"[error: {e}]"
                pipeline.send(plan_progress_msg(step_no, total, "error"))
        pipeline.send(plan_progress_msg(total, total, "complete"))
        return "Plan complete, boss."
