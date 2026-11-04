# Jarvis

A Windows voice assistant with an Electron interface, local automation, a Python backend, and an optional phone/cloud companion.

## Models and execution

- Text routing, conversation, architectural planning, coding, and repair use Groq `openai/gpt-oss-120b`.
- The existing five-key Groq pool handles key failover and cooldowns.
- Project code runs locally after approval, with generated-code validation, project-path checks, a cleaned environment, and execution timeouts.
- The coding workflow has no separate third-party planner or Docker executor.
- Speech, image, and vision features keep their dedicated tooling.

## Local setup

Use Python 3.11+, Node.js/npm, and Windows. Create `backend/.venv`, install `backend/requirements.txt`, and install frontend dependencies with `npm ci` from the repository root. Copy `.env.example` to `.env` and configure your Groq keys privately, or use the Windows DPAPI vault.

Start the desktop interface with `npm start`. Electron starts the backend and supplies its local authentication token. See [SECURITY.md](SECURITY.md) for manual startup, private configuration, remote gateway requirements, and secret-scanning setup.

Cloud connectivity is disabled by default. Configure a fresh shared token and HTTPS/WSS on the server and clients before enabling it.

Never commit credentials, personal conversations, contact lists, or runtime databases. They belong in ignored private configuration and `backend/data`.

New installations start without saved locations or shopping watches. Configure your
own preferences; private delivery coordinates can be stored in
`backend/data/delivery_locations.json`, which is excluded from Git. The APK
installer requires your own `GITHUB_TOKEN` and `GITHUB_REPOSITORY` settings.
