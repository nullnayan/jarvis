# Security and private configuration

Use environment variables or the Windows DPAPI vault for credentials. Copy
`.env.example` to `.env` locally; keep this file and all runtime data private.
The installer reads `GITHUB_TOKEN` or `GH_TOKEN` from its process environment.
Android clients require the server address and token in their settings; builds
must never contain a shared production credential.

## Private data

Every installation must supply its own credentials and account identifiers.
Environment files, encrypted vaults, runtime databases, conversations, contacts,
recordings, screenshots, private backups, and local development notes are not
part of this repository. Never place credentials or personal data in an issue.

## Hosting

Publishing the source is separate from exposing the service. Keep local services
on loopback. Configure authentication, a firewall, and encrypted transport before
using a remote gateway. Remote clients require HTTPS/WSS. Set `CLOUD_ENABLED=true`
only after rotating credentials on the server and all clients. Set the gateway
hostname and TLS port in `CLOUD_HOST`/`CLOUD_PORT`, and the HTTPS base in `CLOUD_URL`.
Twilio requests require valid signatures using the exact public
`TWILIO_WEBHOOK_BASE`. Browser clients require explicit `CLOUD_ALLOWED_ORIGINS`.

The Electron launcher creates a private per-session token for the loopback-only
desktop WebSocket and passes it to its Python child. For separate manual startup,
set the same randomly generated `JARVIS_LOCAL_AUTH_TOKEN` (32+ characters) in both
process environments. Neither the renderer nor a browser receives this token.

This cleanup is not a complete application security audit.

## Before committing

Install Gitleaks from its official release and run `git config core.hooksPath .githooks`
in your clone. The hook scans staged changes before committing. GitHub Actions
also scans full history and runs the focused security tests. The narrow rule in
`.gitleaks.toml` excludes only literal empty example variable labels accidentally
captured across lines; credential values are still scanned.

## Model and code execution

Text routing, conversation, project planning, code generation, and repair use
Groq `openai/gpt-oss-120b` with the existing Groq key failover pool. Generated
project scripts execute locally after user approval, with project-path checks,
secret-access validation, a cleaned process environment, and a timeout. The
former separate provider/container architecture has been removed.

Report a vulnerability privately through the repository owner's GitHub profile.
Do not include credentials, private conversations, or user data in public issues.
