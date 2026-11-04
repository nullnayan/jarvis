import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class CodingAgentTests(unittest.TestCase):
    def test_fix_or_resume_detection_does_not_raise(self):
        from tools.coding_agent import CodingAgent

        agent = CodingAgent.__new__(CodingAgent)
        self.assertTrue(agent._is_fix_or_resume("fix the error in my project"))
        self.assertFalse(agent._is_fix_or_resume("build a portfolio website"))

    def test_generated_code_cannot_reach_jarvis_internals(self):
        from llm.code_executor import validate_generated_code

        blocked_sources = (
            "from security.vault import load_secrets",
            "import config",
            "result = eval('1 + 1')",
            "result = __import__('os')",
        )
        for source in blocked_sources:
            with self.subTest(source=source):
                valid, reason = validate_generated_code(source)
                self.assertFalse(valid)
                self.assertTrue(reason)

    def test_safe_generated_code_is_allowed(self):
        from llm.code_executor import validate_generated_code

        valid, reason = validate_generated_code("print('hello')")
        self.assertTrue(valid)
        self.assertEqual(reason, "")

    def test_planner_and_coder_prompts_support_sqlite_and_auth(self):
        """Verify PLANNER_PROMPT and STEP_CODER_PROMPT require SQLite (app.db), auth, and protected routes."""
        from llm.coding_prompts import PLANNER_PROMPT, STEP_CODER_PROMPT

        # Planner prompt rules
        self.assertIn("sqlite3", PLANNER_PROMPT)
        self.assertIn("app.db", PLANNER_PROMPT)
        self.assertIn("CREATE TABLE IF NOT EXISTS users", PLANNER_PROMPT)
        self.assertIn("login_required", PLANNER_PROMPT)
        self.assertIn("/api/register", PLANNER_PROMPT)
        self.assertIn("/api/login", PLANNER_PROMPT)
        self.assertIn("MongoDB", PLANNER_PROMPT)
        self.assertIn("PostgreSQL", PLANNER_PROMPT)

        # Step coder prompt rules
        self.assertIn("sqlite3", STEP_CODER_PROMPT)
        self.assertIn("app.db", STEP_CODER_PROMPT)
        self.assertIn("CREATE TABLE IF NOT EXISTS users", STEP_CODER_PROMPT)
        self.assertIn("login_required", STEP_CODER_PROMPT)
        self.assertIn("generate_password_hash", STEP_CODER_PROMPT)
        self.assertIn("list of plain single-quoted lines", STEP_CODER_PROMPT)

    def test_login_register_script_has_sqlite_init_and_protected_route(self):
        """Verify a generated server script for a login/register app initializes SQLite and protects routes."""
        import tempfile
        import shutil
        from llm.code_executor import validate_generated_code

        temp_dir = tempfile.mkdtemp()
        db_file = os.path.join(temp_dir, "app.db").replace("\\", "/")

        script = f'''
import os
import sqlite3
from functools import wraps
from flask import Flask, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = "test-secret"
DB_PATH = r"{db_file}"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        db.commit()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({{"error": "Unauthorized", "message": "Please login first"}}), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {{}}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({{"error": "Username and password required"}}), 400
    hashed = generate_password_hash(password)
    with get_db() as db:
        cur = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
        db.commit()
        session["user_id"] = cur.lastrowid
        session["username"] = username
        return jsonify({{"id": cur.lastrowid, "username": username}}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {{}}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return jsonify({{"id": user["id"], "username": user["username"]}}), 200
    return jsonify({{"error": "Invalid credentials"}}), 401

@app.route("/api/profile", methods=["GET"])
@login_required
def profile():
    return jsonify({{"user_id": session["user_id"], "username": session["username"]}})
'''
        try:
            # 1. Must pass Jarvis static security validation
            valid, reason = validate_generated_code(script)
            self.assertTrue(valid, f"Generated script blocked: {reason}")

            # 2. Must compile cleanly
            compiled = compile(script, "<test_script>", "exec")
            self.assertIsNotNone(compiled)

            # 3. Must execute and initialize tables
            scope = {"__name__": "__main__"}
            exec(compiled, scope)
            init_fn = scope.get("init_db")
            self.assertTrue(callable(init_fn))
            init_fn()

            get_db = scope.get("get_db")
            with get_db() as db:
                tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                self.assertIn("users", tables)
                self.assertIn("posts", tables)

            # 4. Protected route must return 401 when unauthenticated
            app = scope.get("app")
            client = app.test_client()
            resp = client.get("/api/profile")
            self.assertEqual(resp.status_code, 401)
            self.assertIn("Unauthorized", resp.get_json().get("error", ""))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
