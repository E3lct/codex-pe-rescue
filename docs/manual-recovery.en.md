# Manual Recovery Guide

[中文](manual-recovery.md) · [Back to the project home](../README.en.md)

This guide is for users who want to run the commands themselves. If an assistant can access local files and run commands, start with the AI-guided option on the project home page. All paths and IDs below are fictional. Recovery workspaces, configs, inspection output, and receipts may contain private data; keep them outside the repository.

## 1. Check the prerequisites

**Action:** Prepare an offline copy of the old `.codex` folder and restore the actual project source files to the destination computer. Start and sign in to the new Codex installation once, then exit it so it creates its own profile and databases.

**Expected result:** You have a readable old backup, restored project folders, and an initialized Codex destination profile.

**Notes:** Python 3.11 or later is required. The modifying `apply` and `rollback` commands run only on Windows. Do not copy the old `auth.json` to sign in. Keep the recovery workspace outside the public repository. This tool does not restore project source code, account credentials, old skills/plugins, ChatGPT cloud history, or image/external attachment binaries.

## 2. Inspect the backup and compatibility

**Action:** Confirm the Python version, then open an independent PowerShell in this repository. `E:\RecoveredProfile\.codex` is a fictional backup path.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[zstd]"
.\.venv\Scripts\codex-pe-rescue.exe inspect --source-home 'E:\RecoveredProfile\.codex'
```

If `python` points to a version older than 3.11 or to a different installation, locate a suitable interpreter and use its full path to run `-m venv .venv`. Then use `.venv\Scripts\python.exe` for the remaining commands.

**Expected result:** `inspect` lists recognized projects, roots, chat titles, and IDs. This output may contain private information.

**Notes:** Project names and chat titles can differ. Identify the intended records by title, path, and content rather than guessing from names. The read-only `inspect` command can provide a limited view of the main database when some databases are missing.

The write adapter expects these data files in the source and destination:

| Location | Purpose |
| --- | --- |
| `state_5.sqlite` | Projects, project roots, threads, and related records |
| `thread_history_1.sqlite` | Projected and real-time conversation history |
| `sqlite/codex-dev.db` | Desktop conversation catalog and sync state |
| `sessions/` | Session records and segments required by selected chats |

Database schemas, migration records, and `user_version` must match between source and destination. Matching filenames do not prove compatibility. The tool stops on incompatible data. Do not edit database version markers. This tool works with a raw offline profile copy; renaming a ZIP file does not turn it into a supported migration package.

## 3. Select records and map paths

**Action:** Copy [`examples/config.json`](../examples/config.json) outside the repository and edit it using the `inspect` results. All user directories, project paths, and IDs below are fictional:

```json
{
  "source_home": "E:\\RecoveredProfile\\.codex",
  "target_home": "C:\\Users\\ExampleUser\\.codex",
  "project_ids": ["replace-with-project-id-from-inspect"],
  "thread_ids": [],
  "path_map": {
    "D:\\Projects\\sample": "E:\\Projects\\sample"
  }
}
```

**Expected result:** `project_ids` selects a project and its chats; `thread_ids` can add individual chats. Select at least one project or chat. `path_map` maps old project roots and chat working directories to their current locations. Add an explicit identity mapping even when a directory has not moved.

**Notes:** To restore only a single chat, set `project_ids` to `[]`. When multiple mappings match, the longest old path prefix wins. Destination folders must already exist and contain the actual project files. Do not guess paths. Managed paths must be shorter than 240 characters; managed paths through symbolic links or directory junctions are rejected.

## 4. Prepare and verify the preview

**Action:** Choose a new workspace outside the repository, such as `E:\rescue-work-01`:

```powershell
.\.venv\Scripts\codex-pe-rescue.exe prepare --config 'E:\recovery-config.json' --workspace 'E:\rescue-work-01'
.\.venv\Scripts\codex-pe-rescue.exe verify --workspace 'E:\rescue-work-01'
```

**Expected result:** The workspace contains `preview.json` and `plan.json`. The preview lists selected records and mapped paths. `verify` returns `"verified": true`, a thread count, and a session segment count.

**Notes:** The workspace must be a new directory. Preparation does not install old records into the current profile. If you change the config or prepared data, prepare and verify again. Do not share the preview or config with others.

## 5. Exit Codex and apply the recovery

**Action:** Keep the independent PowerShell open, save your other work, and fully exit Codex/ChatGPT desktop, Codex CLI, and any editor using a Codex backend. Then run:

```powershell
.\.venv\Scripts\codex-pe-rescue.exe apply --workspace 'E:\rescue-work-01' --yes --codex-stopped
```

**Expected result:** A successful result has `"state": "complete"` and provides a receipt path. A backup is stored under `.codex\pe-rescue-backups` in the destination profile. Reopen Codex after completion and check the selected project and chats.

**Notes:** If a relevant process is detected, the tool reports its name and PID and refuses to write. It does not terminate processes or provide a bypass. Before installation it rebuilds the merge against the latest destination data; duplicate thread IDs or conflicting files stop the operation. Cross-volume files are copied and verified before replacement within the destination directory. Installation spans multiple files and is not atomic against power loss. If an error occurs, inspect the receipt state. `rollback_incomplete` requires manual review. Keep the original backup, workspace, and receipt; do not retry blindly.

## 6. Undo a completed recovery

**Action:** Only while Codex and related clients remain closed and the destination has not changed since recovery, use the actual receipt path:

```powershell
.\.venv\Scripts\codex-pe-rescue.exe rollback --receipt 'C:\Users\ExampleUser\.codex\pe-rescue-backups\replace-with-actual-backup\receipt.json' --yes --codex-stopped
```

**Expected result:** A successful rollback returns `"state": "rolled_back"`.

**Notes:** Automatic rollback only supports a completed recovery whose destination fingerprint remains unchanged. After opening the client, creating a chat, or changing records, the tool refuses automatic rollback to protect newer data. Do not manually edit receipt states to bypass this guard. See the [recovery model and failure states](recovery-model.md).

## 7. Run the tests

**Action:** After installing `.[zstd]` in the Python environment, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**Expected result:** Synthetic-data tests pass, including plain and compressed sessions, WAL snapshots, offset recalculation, conflict detection, interrupted installation, and rollback.

**Notes:** Tests do not use a real profile and cannot prove compatibility with every current or future Codex database version. Keep personal data out of the repository before and after testing.
