---
name: codex-pe-rescue
description: Recover selected local Codex projects and chats from a raw offline .codex backup after system failure or relocation. Prepares its own pinned engine, preview and exit-safe launcher without a separate checkout. Not for ChatGPT cloud history.
---

# Recover local Codex history with minimal user work

This is also the entrypoint for an assistant given the repository URL and asked to recover history. Skill installation is optional. For a repository-link request, the concise entrypoints are the [README](../../README.md) and [AI guide](../../AGENTS.md); this Skill remains the full recovery workflow. Read [references/assistant-workflow.md](references/assistant-workflow.md) for commands and handoff details. If browsing the repository rather than using an installed Skill, read and download `scripts/assist.py` into a private local tool directory yourself. Do not ask the user to install this Skill or download a second project.

Own the preparation work. The user should describe the backup and intended chats, not find internal IDs, write JSON, install Git or edit SQL. The helper finds a nearby engine or downloads a fixed GitHub commit and verifies its SHA-256. It prepares dependencies in an isolated user cache. Use Python 3.11+ already available locally or supplied by the host (discover the workspace runtime when a tool exists). If none is available, explain that single prerequisite and follow the user's software-installation rules; do not claim Python is bundled.

## Find facts before asking

Follow the staged intake and option examples in the project's `docs/guided-recovery-flow.md` when available through the repository link. Prefer the host's structured question component, otherwise short numbered options. Identify raw profile versus migration-package input first only when unknown; do not ask users who already explained their PE/raw-backup situation. Read files before asking, and avoid presenting every stage as an upfront questionnaire.

Reuse paths, preferences and authorization already supplied. Default target to `CODEX_HOME`, otherwise the current user's `.codex`. Check the named backup and source directories with bounded searches. Ask only when facts cannot be established: the backup location, which of several plausible chats is intended, or which new folder corresponds to an old root. Batch related ambiguities with candidate names/paths. Do not ask for IDs, credentials or a config file. Chat subjects may differ from project names; inspect titles and paths first.

## Prepare, show, hand off, verify

Run helper `inspect` before provisioning dependencies. Confirm the source is offline and destination is initialized; actual project files must already be restored. Run helper `prepare` with selected IDs and explicit mappings, including identity mappings for unchanged roots. It writes the private config, verifies the preview and returns a clickable `Start-Recovery.cmd`. Default workspaces and logs stay in the user's local application-data cache, outside this public checkout. Treat inspection output and all generated files as private.

Show a plain-language preview: selected projects/chat counts, old-to-new folders, existing history preserved, and image/attachment limitations. Ask for approval only when the user's rules require it, after this concrete preview exists; otherwise use existing task authorization. Do not repeatedly ask to prepare the engine, config or launcher when already in scope.

Provide the exact launcher link. Tell the user: **double-click it first, keep the window open, fully exit Codex, wait for `RECOVERY COMPLETE`, then reopen Codex**. If opening it is authorized, use an independent visible terminal the user can see. Do not wait synchronously in the current Codex terminal or terminate the client yourself. The runner requires 10 quiet seconds, repeats process guards during writes, saves the result and pauses after success/failure.

After reopening, run helper `status` to read the saved outcome instead of asking the user to transcribe the console. A ready preview, started launcher or missing outcome is not recovery success. Confirm `complete` and check the intended sidebar/chat if available.

Stop on incompatible schema, unresolved mappings, conflicting IDs, changed hashes or corrupt/missing segments. Do not bypass checks or edit migration markers. If the engine reports `rollback_incomplete`, or a run was interrupted during `installing`, keep the client closed and inspect receipts/backups before further writes. Never replay archived WAL onto standalone snapshots. Immediate undo uses the engine's documented rollback command in an independent terminal and requires an unchanged completed destination; do not bypass rejection after newer activity.

Actual source files, images/external attachment binaries, cloud history, credentials and old skills/plugins are not restored by this engine. Do not copy old execution permissions or secrets. Preserve the original offline backup and never upload real profiles or recovery artifacts.
