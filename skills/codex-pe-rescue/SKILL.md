---
name: codex-pe-rescue
description: Recover selected local Codex projects and chats from a raw offline .codex backup after system failure or relocation, with path mapping, preview and a separate-terminal installation handoff. Uses the codex-pe-rescue engine; not for ChatGPT cloud history.
---

# Recover an offline Codex profile

Use a locally installed `codex-pe-rescue` engine or an available checkout of this project. Locate it and read its README and `docs/recovery-model.md` before writing. This skill folder alone contains no recovery engine. If no engine is available, explain that dependency and obtain the public project through the user's chosen installation method; do not invent database-editing commands or execute unreviewed downloaded scripts.

Confirm the source is a preserved offline profile, the destination is the user's initialized current profile, and actual project source files have been restored separately. Respect any existing authorization or review requirement. Do not copy credentials or replace the entire destination profile.

Use `inspect --source-home <backup>` to identify native project IDs, chat titles and historical roots. Treat its output as private. A chat's subject may differ from its project's name. If the intended chat is ambiguous, show a small selection of plausible titles and ask rather than import unrelated projects.

Prepare a private JSON configuration with `source_home`, `target_home`, `project_ids` and/or `thread_ids`, and explicit `path_map`. Use the longest applicable prefix; include identity mappings for unchanged locations. Cover selected roots and working directories. Keep config, workspaces, previews and logs outside the public checkout. Do not upload any source backup or inspect output.

Run `prepare --config <config> --workspace <new-directory>` and `verify --workspace <directory>`. Review counts, exact chosen IDs, path destinations and attachment limitations. Source and target schemas must match. Stop on unsupported schema, unresolved mapping, conflicting IDs, corrupt segments or incomplete history dependencies; do not remove checks or edit migration markers to force recovery.

Before installation, explain concrete selected records, mapped roots and the backup location to the user. Obtain approval if the user's existing instructions require review; existing task authorization otherwise applies. The current Codex process cannot safely write its own live profile. Arrange an independent terminal with the engine path and exact prepared workspace, then have the user fully exit desktop/CLI/IDE backends before running:

```text
codex-pe-rescue apply --workspace <prepared-directory> --yes --codex-stopped
```

Do not kill unrelated processes, bypass process detection, or claim recovery just because a launcher started. Retain the returned receipt and require `state: complete` before reopening. If the command reports `rollback_incomplete`, or was killed while `installing`, keep the client closed and inspect snapshots/receipt before further writes. Never replay saved WAL onto standalone backup snapshots.

After reopening, verify the intended sidebar project, an old chat and its mapped source directory. Explain that images/external attachment binaries, cloud history, source files and old skills/plugins are not restored by this engine. Do not automatically copy old execution permissions or secrets.

An immediate undo uses `rollback --receipt <returned-path> --yes --codex-stopped` from the independent terminal. It requires a completed recovery and unchanged destination; do not bypass rejection after newer activity. Preserve backups for manual review instead.
