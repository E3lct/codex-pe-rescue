# Codex PE Rescue

[中文说明](README.md)

Recover selected local Codex projects and chat history from a **raw offline `.codex` backup**, including files rescued with Windows PE after an unbootable system. No export package from the old system is required. Restore your actual project source files separately, then map old paths to their new locations.

**Experimental v0.1, Windows write adapter.** This is an independent tool for an internal, version-dependent storage format, not an official OpenAI import API. It requires native `projects`, `project_roots`, and `threads` tables in `state_5.sqlite`, `thread_history_1.sqlite`, and `sqlite/codex-dev.db`. Source and target schemas and migration records must match exactly. Older JSON-only project registries and schema conversion are unsupported.

## Quick start

Use an independent PowerShell in this repository. All paths and identifiers below are fictional examples. Keep recovery workspaces and configuration outside the public repository.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[zstd]"
.\.venv\Scripts\codex-pe-rescue.exe inspect --source-home 'E:\RecoveredProfile\.codex'
```

Requires Python 3.11+. Choose the projects/threads identified by inspection and edit a private copy of [examples/config.json](examples/config.json):

```json
{
  "source_home": "E:\\RecoveredProfile\\.codex",
  "target_home": "C:\\Users\\ExampleUser\\.codex",
  "project_ids": ["replace-with-project-id-from-inspect"],
  "thread_ids": [],
  "path_map": {"D:\\Projects\\sample": "E:\\Projects\\sample"}
}
```

Select at least one project or thread. Supply mappings for all selected roots and working directories, including identity mappings for unchanged locations. Longest matching prefixes win. Actual destination project directories must already exist. Initialize the new Codex installation normally first; do not copy old credentials to sign in.

```powershell
.\.venv\Scripts\codex-pe-rescue.exe prepare --config 'E:\recovery-config.json' --workspace 'E:\rescue-work-01'
.\.venv\Scripts\codex-pe-rescue.exe verify --workspace 'E:\rescue-work-01'
```

Review `preview.json` and `plan.json` in the new workspace. Preparation does not install records. The frozen inputs and engine are hashed; recreate the workspace after changing either.

Keep the independent terminal open, fully exit Codex/ChatGPT desktop, CLI, and IDE backends, then:

```powershell
.\.venv\Scripts\codex-pe-rescue.exe apply --workspace 'E:\rescue-work-01' --yes --codex-stopped
```

The tool checks relevant process names/PIDs and refuses live writes. It never terminates processes. It rebuilds the merge using the latest target data, preserves existing threads and authentication/configuration files, and rejects duplicate thread IDs or conflicting session files. Wait for `state: complete`, retain the returned receipt, then reopen the client.

Backups are stored under the target `.codex\pe-rescue-backups`. To undo a completed recovery while the client is still closed and the destination is unchanged:

```powershell
.\.venv\Scripts\codex-pe-rescue.exe rollback --receipt '<returned receipt path>' --yes --codex-stopped
```

New target changes block automatic rollback. A failed install may report `rolled_back` or `rollback_incomplete`; the latter requires manual review. Do not reopen a partially restored profile or retry blindly. Preserve the source, workspace, receipt and backup.

## Scope and limits

- Captures original databases and sidecars before opening SQLite, without opening the original backup through SQLite.
- Handles plain/Zstandard session segments, dependent history bases and byte-offset recalculation. Preserves message body bytes; rewrites structured working-directory/runtime metadata only.
- Reuses matching destination projects or imports selected project records. Does not merge divergent histories with the same ID.
- Snapshots incorporate WAL; archived WAL is diagnostic only and is never reattached to standalone snapshots.
- Copies across volumes, verifies hashes, and replaces within the destination directory. A multi-file install is **not** power-loss atomic.
- Windows modifying commands only. Managed paths must be shorter than 240 characters; linked managed paths are rejected.
- No ChatGPT cloud recovery, project-source copying, credential migration, plugin/skill installation, image/external attachment binary recovery, or database-version conversion.
- Runtime recovery makes no network calls. Installation downloads dependencies. Workspaces, inspection output and backups contain private information.

The included [Skill](skills/codex-pe-rescue/SKILL.md) guides another assistant through selection and the separate-terminal handoff. Install its folder manually if desired; it requires this engine installed or available in a checkout.

## Tests and provenance

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use synthetic databases and sessions, including compressed records, WAL capture, interrupted installation, rollback, tampering and compatibility checks. They do not establish compatibility with every live Codex release. This public engine is a generic rewrite of a one-off recovery approach; no user profile or private incident artifacts are shipped.

Read the [recovery model](docs/recovery-model.md), [provenance](PROVENANCE.md), [contribution guide](CONTRIBUTING.md) and [security guidance](SECURITY.md). Source code is [MIT licensed](LICENSE). User data is not licensed for publication. Not affiliated with OpenAI or other recovery-tool authors.
