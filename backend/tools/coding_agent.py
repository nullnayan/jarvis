# FILE: backend/tools/coding_agent.py
# Agentic multi-step coding pipeline with planner, step coder, live narration, self-healing, and project repair.

import os
import sys
import re
import json
import time
import tempfile
import asyncio
import subprocess
from logger import get_logger
from config import (
    CODING_AGENT_MODEL,
    CODING_MAX_RETRIES,
    CODING_STEP_TIMEOUT,
)
from llm.coding_prompts import PLANNER_PROMPT, STEP_CODER_PROMPT, ERROR_RECOVERY_PROMPT, REPAIR_PROMPT, render_coding_prompt
from llm.code_executor import validate_generated_code, _clean_environment

_log = get_logger(__name__)
print = _log.info

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LAST_PROJ_FILE = os.path.join(DATA_DIR, "last_project.json")

class CodingAgent:
    def __init__(self, brain, pipeline):
        self.brain = brain
        self.pipeline = pipeline
        self.is_running = False
        self.current_task = ""
        self.current_step = 0
        self.total_steps = 0
        self.project_dir = ""
        self.created_files = []
        self.completed_steps = []
        self.plan = []
        self.last_failed_step = None
        self.last_error = ""
        self.last_code = ""
        self.pending_installs = None  # List of packages awaiting user approval, or None when idle
        self.pending_plan_approval = None  # Awaiting user approval to proceed with generated plan
        self._load_last_project()

    def _load_last_project(self):
        """Loads last active project metadata from disk."""
        try:
            if os.path.exists(LAST_PROJ_FILE):
                with open(LAST_PROJ_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pdir = data.get("project_dir", "")
                    if pdir and os.path.exists(pdir):
                        self.project_dir = pdir
                        self.current_task = data.get("task", "")
                        self.created_files = data.get("created_files", [])
                        self.last_error = data.get("last_error", "")
                        self.last_code = data.get("last_code", "")
        except Exception:
            pass

    def _save_project_state(self):
        """Persists current project state to disk."""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = {
                "project_dir": self.project_dir,
                "task": self.current_task,
                "created_files": self.created_files,
                "completed_steps": self.completed_steps,
                "last_error": self.last_error,
                "last_code": self.last_code,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(LAST_PROJ_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CodingAgent] Save state error: {e}")

    def get_status(self) -> str:
        """Returns live progress for user status queries."""
        if not self.is_running:
            if self.project_dir:
                return f"Currently idle, boss. Last project was {os.path.basename(self.project_dir)}."
            return "I am not actively working on any coding project right now, boss."
        step_desc = self.plan[self.current_step - 1]["description"] if (0 < self.current_step <= len(self.plan)) else "development"
        return f"I am currently building your project, boss. Step {self.current_step} of {self.total_steps}: {step_desc}."

    def _is_fix_or_resume(self, task: str) -> bool:
        """Detects whether user wants to solve an error or continue the existing project."""
        txt = (task or "").lower()
        repair_triggers = [
            "solve that error", "solve the error", "solve all errors", "solve errors",
            "fix the error", "fix this error", "fix all errors", "fix errors",
            "resolve the error", "resolve error", "resolve all errors", "solve error", "debug",
            "restart server", "restart the server", "run again", "continue",
            "identify and resolve", "fix the project", "repair", "run this project",
            "run the project", "solve the problem", "solve problem", "make it work"
        ]
        return any(trig in txt for trig in repair_triggers)

    def _determine_project_dir(self, task: str) -> str:
        """Derives a clean, sensible project directory path on the Desktop."""
        user_desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        clean = task.lower()

        if any(w in clean for w in ["amazon", "flipkart", "ecommerce", "e-commerce", "shopping", "store", "shoes", "shoe"]):
            proj_name = "ecommerce-store"
        elif any(w in clean for w in ["portfolio", "resume", "personal website"]):
            proj_name = "portfolio-website"
        elif any(w in clean for w in ["restaurant", "food", "cafe"]):
            proj_name = "restaurant-webapp"
        elif any(w in clean for w in ["chat", "messaging", "whatsapp"]):
            proj_name = "chat-application"
        elif any(w in clean for w in ["blog", "article"]):
            proj_name = "blog-platform"
        elif any(w in clean for w in ["dashboard", "analytics", "admin"]):
            proj_name = "admin-dashboard"
        elif any(w in clean for w in ["game", "arcade"]):
            proj_name = "web-game"
        else:
            stop_words = {"make", "build", "create", "a", "an", "the", "for", "in", "on", "website", "project", "app", "new", "web", "eg", "like", "just", "and", "to"}
            words = [w for w in re.sub(r'[^\w\s-]', '', clean).split() if w not in stop_words and len(w) > 2]
            proj_name = "-".join(words[:2]) if words else "jarvis-project"

        path = os.path.join(user_desktop, proj_name)
        os.makedirs(path, exist_ok=True)
        return path

    async def repair_project(self, task_description: str, lang: str = "en"):
        """In-place error resolution and server recovery for the active project."""
        self.is_running = True
        try:
            # Ensure we have a valid project directory
            if not self.project_dir or not os.path.exists(self.project_dir):
                # Search Desktop for latest created project
                user_desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                recent_dir = None
                recent_time = 0
                for d in os.listdir(user_desktop):
                    full_p = os.path.join(user_desktop, d)
                    if os.path.isdir(full_p) and not d.startswith("."):
                        mt = os.path.getmtime(full_p)
                        if mt > recent_time:
                            recent_time = mt
                            recent_dir = full_p
                if recent_dir:
                    self.project_dir = recent_dir
                else:
                    self.project_dir = os.path.join(user_desktop, "ecommerce-store")
                    os.makedirs(self.project_dir, exist_ok=True)

            proj_name = os.path.basename(self.project_dir)
            print(f"[CodingAgent] Repairing existing project in: {self.project_dir}")
            await self.pipeline.respond(f"Diagnosing and resolving the issue in your {proj_name} project, boss.", lang=lang)

            existing_files = os.listdir(self.project_dir) if os.path.exists(self.project_dir) else []
            files_str = ", ".join(existing_files) if existing_files else "None yet"

            prompt = render_coding_prompt(REPAIR_PROMPT,
                project_dir=self.project_dir,
                task=task_description,
                existing_files=files_str,
                last_error=self.last_error or "Unknown runtime error",
                last_code=self.last_code or "None"
            )

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Fix all issues in {self.project_dir} and ensure the project is running on localhost."}
            ]

            repair_code = await self.brain._chat_with_failover(
                CODING_AGENT_MODEL, messages,
                clients=self.brain._coder_clients(),
                temperature=0.2, max_tokens=4000
            )
            repair_code = self.brain._clean_code(repair_code)

            result = await self._run_script(repair_code)
            if result["success"]:
                print(f"[CodingAgent] Repair successful: {result['stdout']}")
                self.last_error = ""
                self._save_project_state()
                msg = f"Resolved the issue, boss. {result['stdout'] or 'Project is running.'}"
                await self.pipeline.respond(msg, lang=lang)
            else:
                err = result["stderr"] or result["stdout"]
                print(f"[CodingAgent] First repair attempt failed: {err[:200]}")
                # Retry repair once with error feedback
                fix_prompt = f"The previous repair code failed with:\n{err}\nWrite the corrected script to fix {self.project_dir}."
                messages.append({"role": "user", "content": fix_prompt})
                repair_code2 = await self.brain._chat_with_failover(
                    CODING_AGENT_MODEL, messages,
                    clients=self.brain._coder_clients(),
                    temperature=0.2, max_tokens=4000
                )
                repair_code2 = self.brain._clean_code(repair_code2)
                result2 = await self._run_script(repair_code2)
                if result2["success"]:
                    self.last_error = ""
                    self._save_project_state()
                    await self.pipeline.respond(f"Resolved the issue, boss. {result2['stdout'] or 'Project is running.'}", lang=lang)
                else:
                    self.last_error = result2["stderr"]
                    self._save_project_state()
                    await self.pipeline.respond("I attempted to resolve the error, boss, but encountered a secondary issue.", lang=lang)

        except Exception as e:
            print(f"[CodingAgent] Repair error: {e}")
            await self.pipeline.respond("An error occurred while repairing the project, boss.", lang=lang)
        finally:
            self.is_running = False

    async def execute_task(self, task_description: str, lang: str = "en"):
        """Main agentic loop: plan -> execute -> narrate -> self-heal."""
        if self._is_fix_or_resume(task_description):
            return await self.repair_project(task_description, lang=lang)

        self.is_running = True
        self.current_task = task_description
        self.current_step = 0
        self.created_files = []
        self.completed_steps = []
        self.last_error = ""
        self.last_code = ""
        self.project_dir = self._determine_project_dir(task_description)
        self._save_project_state()

        print(f"[CodingAgent] Starting project: '{task_description}'")
        print(f"[CodingAgent] Project directory: {self.project_dir}")

        try:
            # Step 1: Architectural Planning & Specification Enhancement
            await self.pipeline.respond("Analyzing project architecture and creating development plan, boss.", lang=lang)

            # [Stage 1] Expand weak prompt into rich flagship spec via Groq gpt-oss-120b
            from llm.prompt_enhancer import enhance_prompt
            from server.messages import enhanced_prompt_msg, caption_msg

            # Only spend the enhancement round-trip on weak prompts — a clear,
            # detailed specification the user already wrote doesn't need expanding.
            words = task_description.split()
            weak_prompt = len(words) < 25 and not any(
                w in task_description.lower() for w in
                ["with ", "using ", "include", "feature", "step", "database",
                 "authentication", "login", "payment", "responsive", "api"]
            )
            if weak_prompt:
                enhanced_spec = await enhance_prompt(task_description, self.brain)
            else:
                enhanced_spec = ""
                print("[CodingAgent] Prompt already detailed — skipping enhancement.")
            if enhanced_spec:
                try:
                    print(f"\n{'='*70}\n[Jarvis Terminal] ENHANCED SPECIFICATION:\n{enhanced_spec}\n{'='*70}\n")
                except UnicodeEncodeError:
                    print(f"\n{'='*70}\n[Jarvis Terminal] ENHANCED SPECIFICATION (Sanitized):\n{enhanced_spec.encode('ascii', errors='replace').decode('ascii')}\n{'='*70}\n")
                self.pipeline.send(enhanced_prompt_msg(enhanced_spec))
                first_line = enhanced_spec.split("\n")[0].strip("# ").strip()
                if first_line:
                    self.pipeline.send(caption_msg(f"Spec: {first_line[:80]}..."))

            # Generate the project plan with Groq GPT-OSS 120B.
            plan_data = await self._generate_plan(task_description, enhanced_spec=enhanced_spec)
            self.plan = plan_data.get("steps", [])
            required_installs = plan_data.get("required_installs", [])
            self.total_steps = len(self.plan)

            if not self.plan:
                await self.pipeline.respond("I had trouble generating the project plan, boss. Falling back to direct generation.", lang=lang)
                self.is_running = False
                return

            # Plan Review: Present plan to user and ask for confirmation before executing
            plan_summary = "; ".join([f"Step {s.get('step', i+1)}: {s.get('description', '')}" for i, s in enumerate(self.plan)])
            print(f"[CodingAgent] Presenting plan ({self.total_steps} steps) for user review:\n{plan_summary}")
            self.pending_plan_approval = True
            await self.pipeline.respond(
                f"I've designed a {self.total_steps}-step plan, boss: {plan_summary}. Should I proceed with development?",
                lang=lang,
            )
            while self.pending_plan_approval is True:
                await asyncio.sleep(0.5)
            if self.pending_plan_approval == "declined":
                print("[CodingAgent] Plan execution declined by user.")
                self.pending_plan_approval = None
                self.is_running = False
                return
            self.pending_plan_approval = None

            # Check and handle required installs proposed by the planner.
            # NEVER auto-install — always ask the user for explicit confirmation first.
            if required_installs:
                from llm.project_context import get_sanitized_package_inventory
                installed = set(get_sanitized_package_inventory())
                missing = [p for p in required_installs if p.lower() not in installed]
                if missing:
                    pkg_names = ", ".join(missing)
                    print(f"[CodingAgent] Plan proposes external dependencies: {pkg_names}")
                    # Pause the coding agent and ask for explicit approval.
                    self.pending_installs = missing
                    await self.pipeline.respond(
                        f"The plan needs {len(missing)} packages: {pkg_names}. Should I install them, boss?",
                        lang=lang,
                    )
                    # Wait for the user's yes/no. The pipeline's confirmation gate
                    # sets pending_installs to True (approve) or False (decline).
                    while isinstance(self.pending_installs, list):
                        await asyncio.sleep(0.5)
                    if self.pending_installs is False:
                        print("[CodingAgent] User declined dependency installation. Proceeding without them.")
                    else:
                        print("[CodingAgent] User approved dependency installation.")
                        await self._install_packages(missing)
                    # Always return to idle: a leftover non-None value would make
                    # the pipeline's install-confirmation gate swallow every later
                    # command with "awaiting yes/no".
                    self.pending_installs = None

            plan_intro = f"I've broken this down into {self.total_steps} development steps, boss. Starting now."
            await self.pipeline.tts.speak(plan_intro, lang=lang)

            # Guaranteed workspace setup: create the project folder and open it in
            # VS Code BEFORE any files are written. This way the user sees the empty
            # folder open in the editor, then watches each file appear live as the
            # steps run — regardless of what the planner generated for step 1.
            try:
                os.makedirs(self.project_dir, exist_ok=True)
                print(f"[CodingAgent] Opening project folder in VS Code: {self.project_dir}")
                await self.pipeline.tts.speak(f"Opening the project folder in VS Code, boss.", lang=lang)
                subprocess.Popen(["code", self.project_dir], shell=False)
                await asyncio.sleep(2.0)
            except Exception as e:
                print(f"[CodingAgent] Could not open VS Code: {e}")

            # Step 2: Sequential Step Execution
            for i, step in enumerate(self.plan):
                self.current_step = i + 1
                step_desc = step.get("description", f"Step {self.current_step}")
                target_file = step.get("target_file")
                narration = step.get("narration", f"Step {self.current_step} completed, boss.")

                print(f"\n{'='*60}")
                print(f"[CodingAgent] Executing Step {self.current_step}/{self.total_steps}: {step_desc}")
                print(f"{'='*60}")

                await self.pipeline.tts.speak(f"Step {self.current_step}: {step_desc}", lang=lang)

                success = False
                last_code = ""
                last_error = ""
                # Model-quality failures (syntax/blocked) are NOT fixable by retry —
                # the model keeps producing the same class of error. Cap those at 2
                # attempts so a broken step can't burn minutes re-attempting.
                quality_failures = 0

                for attempt in range(CODING_MAX_RETRIES):
                    # Stop early for model-quality failures: retrying won't help.
                    if attempt > 0 and quality_failures >= 2:
                        print(f"[CodingAgent] Step {self.current_step} failing with model-quality errors; skipping further retries.")
                        break
                    try:
                        if attempt == 0:
                            code = await self._generate_step_code(step)
                        else:
                            print(f"[CodingAgent] Self-healing attempt {attempt + 1}/{CODING_MAX_RETRIES} for step {self.current_step}...")
                            await self.pipeline.tts.speak(f"Resolving an issue in step {self.current_step}, boss.", lang=lang)
                            code = await self._recover_step_code(step, last_code, last_error)

                        last_code = code
                        self.last_code = code
                        result = await self._run_script(code)

                        if result["success"]:
                            success = True
                            print(f"[CodingAgent] Step {self.current_step} succeeded: {result['stdout'][:120]}")
                            self.completed_steps.append({"step": self.current_step, "description": step_desc, "target_file": target_file})
                            if target_file and target_file not in self.created_files:
                                self.created_files.append(target_file)
                            self._save_project_state()

                            # Live spoken narration of progress
                            await self.pipeline.tts.speak(narration, lang=lang)
                            break
                        else:
                            last_error = result["stderr"] or result["stdout"]
                            self.last_error = last_error
                            self.last_failed_step = step
                            print(f"[CodingAgent] Step {self.current_step} attempt {attempt + 1} failed:\n{last_error[:300]}")
                            # A syntax/blocked error means the model produced bad code —
                            # a codegen quality issue, not a runtime bug worth retrying.
                            if "syntax error" in last_error.lower() or "blocked" in last_error.lower():
                                quality_failures += 1
                    except Exception as step_ex:
                        last_error = str(step_ex)
                        self.last_error = last_error
                        print(f"[CodingAgent] Step {self.current_step} code generation error: {step_ex}")

                if not success:
                    print(f"[CodingAgent] Step {self.current_step} failed after {attempt + 1} attempts. Continuing to next step...")
                    await self.pipeline.tts.speak(f"Step {self.current_step} encountered an issue, boss. Moving to next milestone.", lang=lang)

            print(f"[CodingAgent] All development steps finished for: {task_description}")
            self._save_project_state()
            await self.pipeline.respond(f"Project development completed, boss! Everything is ready in {os.path.basename(self.project_dir)}.", lang=lang)

        except Exception as e:
            print(f"[CodingAgent] Fatal pipeline error: {e}")
            self.last_error = str(e)
            self._save_project_state()
            await self.pipeline.respond("An error occurred during project development, boss.", lang=lang)
        finally:
            self.is_running = False

    async def _generate_plan(self, task: str, enhanced_spec: str = "") -> dict:
        """Generate a project plan through Groq GPT-OSS 120B and its key failover pool."""
        from llm.project_context import _clean_json_plan
        spec_text = enhanced_spec or task
        messages = [
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": f"Project Task: {task}\nProject Directory: {self.project_dir}\n\nSpecification:\n{spec_text}\n\nGenerate the sequential development plan in JSON."},
        ]
        raw = await self.brain._chat_with_failover(
            CODING_AGENT_MODEL, messages, clients=self.brain._coder_clients(),
            temperature=0.2, max_tokens=1800,
        )
        return _clean_json_plan(raw)


    async def _generate_step_code(self, step: dict) -> str:
        """Generates self-contained Python code for a single step with full project context."""
        completed_summary = "; ".join([f"Step {s['step']}: {s['description']}" for s in self.completed_steps]) or "None yet"
        files_summary = ", ".join(self.created_files) or "None yet"

        # Planning and generated step code use the same Groq model/key pool.
        print(f"[CodingAgent] Generating Step {self.current_step} code via fast coder pool...")

        prompt = render_coding_prompt(STEP_CODER_PROMPT,
            task=self.current_task,
            step_num=self.current_step,
            description=step.get("description", ""),
            target_file=step.get("target_file", "None"),
            project_dir=self.project_dir,
            completed_summary=completed_summary,
            files_created=files_summary
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Write the Python script to execute Step #{self.current_step}."}
        ]
        # The Groq client pool handles key cooldowns and failover.
        raw = await self.brain._chat_with_failover(
            "openai/gpt-oss-120b", messages,
            clients=self.brain._coder_clients(),
            temperature=0.2, max_tokens=3500
        )
        code = self.brain._clean_code(raw)
        if code and code.strip():
            return code
        return ""

    async def _recover_step_code(self, step: dict, failed_code: str, error_message: str) -> str:
        """Self-healing: feeds the error traceback back to the fast coder pool for fixed code."""
        completed_summary = "; ".join([f"Step {s['step']}: {s['description']}" for s in self.completed_steps]) or "None yet"
        files_summary = ", ".join(self.created_files) or "None yet"

        print(f"[CodingAgent] Recovering Step {self.current_step} via fast coder pool...")

        prompt = render_coding_prompt(ERROR_RECOVERY_PROMPT,
            step_num=self.current_step,
            task=self.current_task,
            description=step.get("description", ""),
            failed_code=failed_code,
            error_message=error_message
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Write the corrected Python script to fix the error and execute this step successfully."}
        ]
        raw = await self.brain._chat_with_failover(
            "openai/gpt-oss-120b", messages,
            clients=self.brain._coder_clients(),
            temperature=0.2, max_tokens=3500
        )
        code = self.brain._clean_code(raw)
        if code and code.strip():
            return code
        return ""

    async def _install_packages(self, packages: list[str]) -> None:
        """Installs approved packages via pip. Called only after user confirmation."""
        import subprocess
        for pkg in packages:
            try:
                print(f"[CodingAgent] Installing dependency: {pkg}...")
                res = subprocess.run([sys.executable, "-m", "pip", "install", pkg], capture_output=True, timeout=90)
                if res.returncode == 0:
                    print(f"[CodingAgent] Successfully installed: {pkg}")
                else:
                    print(f"[CodingAgent] Failed to install {pkg}: {res.stderr.decode('utf-8', errors='ignore')[:120]}")
            except Exception as pkg_err:
                print(f"[CodingAgent] Error installing {pkg}: {pkg_err}")

    async def _run_script(self, code: str) -> dict:
        """Run approved generated code locally with project-path and secret checks."""
        from llm.project_paths import validate_project_paths
        if not code or not code.strip():
            return {"success": False, "stdout": "", "stderr": "Empty code received"}
        valid, reason = validate_project_paths(code, self.project_dir)
        if not valid:
            return {"success": False, "stdout": "", "stderr": f"Code blocked outside project boundary: {reason}"}
        return await self._run_local_script(code)


    async def _run_local_script(self, code: str) -> dict:
        """Executes trusted Python script in a local temp file with cleaned environment."""
        valid, reason = validate_generated_code(code)
        if not valid:
            return {"success": False, "stdout": "", "stderr": f"Generated code blocked: {reason}"}

        tmp = os.path.join(tempfile.gettempdir(), f"jarvis_step_{self.current_step}_{int(time.time())}.py")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(code)

        venv_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".venv", "Scripts", "python.exe")
        py_exe = venv_py if os.path.exists(venv_py) else sys.executable

        try:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            proc = await asyncio.create_subprocess_exec(
                py_exe, tmp,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_dir,
                env=_clean_environment(),
                creationflags=creationflags,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CODING_STEP_TIMEOUT)
            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()
            return {
                "success": (proc.returncode == 0),
                "stdout": out_str,
                "stderr": err_str
            }
        except asyncio.TimeoutError:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=5,
                    )
                else:
                    proc.kill()
            except Exception as kill_error:
                print(f"[CodingAgent] Failed to terminate timed-out step: {kill_error}")
            return {"success": False, "stdout": "", "stderr": f"Step timed out after {CODING_STEP_TIMEOUT}s"}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e)}
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
