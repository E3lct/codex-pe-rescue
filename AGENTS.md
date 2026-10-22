# AI entrypoint

Read the purpose and safety boundary at the top of `README.md`, then this file. For a recovery request, follow `skills/codex-pe-rescue/SKILL.md`.

## Recovery requests
- A repository link alone is not authorization to recover data; distinguish recovery requests from reading, reviewing, or development tasks.
- Full recovery workflow: `skills/codex-pe-rescue/SKILL.md`.
- Helper: `skills/codex-pe-rescue/scripts/assist.py`.
- Command and handoff details: `skills/codex-pe-rescue/references/assistant-workflow.md`.
- Requires Python 3.11+; prefer a verified local or host runtime and follow the user's installation rules if missing.
- `apply` and `rollback` write only on Windows. The source must be an offline backup; the destination must be initialized and pass compatibility checks.
- Reuse facts already supplied. Inspect files first and ask only about unresolved recovery scope or path mappings.
- Prepare and explain a preview before writing; follow the user's existing authorization and review requirements.
- Use the standalone launcher to wait for client exit. Never kill processes or bypass guards.
- Read the saved outcome and receipt; a preview or started launcher is not a completed recovery.
- Never upload real backups, chats, credentials, or recovery artifacts. Keep private workspaces outside this repository.
- Never replace the whole current `.codex`, overwrite new chats, import old credentials, or force database-version changes.
- On partial installation or incomplete rollback, stop retrying, preserve evidence, and follow the Skill's recovery guidance.

For repository development, follow `CONTRIBUTING.md`, `SECURITY.md`, and `PROVENANCE.md`; use synthetic data only.
