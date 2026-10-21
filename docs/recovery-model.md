# Recovery model and failure boundaries

## Incident pattern

A machine can no longer boot. A recovery environment copies a user's raw `.codex` folder and project source folders to another disk. After reinstalling Windows, the user signs in to Codex and creates new records. Old project locations may have changed drive letters or directory names. Replacing the entire new profile would risk discarding new records and account settings.

This tool treats the old folder as an offline data source and performs a selective merge into an initialized destination. All examples in this repository are fictional. No private incident logs or backups are included.

## Why copying one file is insufficient

Local history can reference several stores: native project ownership, project roots, thread rows, desktop catalog entries, history projections, session segment files, and legacy sidebar metadata. A restored database whose paths or references still point elsewhere may not present the expected sidebar or history. A compressed/segmented session may depend on a preceding segment. Changing structured bytes also changes recorded offsets.

This adapter follows the known relationships and fails on incompatible schema, missing required segments, invalid offsets/records, conflicting thread IDs, or failed integrity checks. It does not claim exhaustive support for future schema additions. Unknown relationships require an adapter update and synthetic tests, not forced insertion.

## Data flow

1. Copy database files and adjacent WAL/SHM to an isolated temporary location before opening SQLite. Snapshot the copies. Copy selected source metadata. Confirm source fingerprints are unchanged.
2. Select native projects or explicit thread IDs, associated descendants, and required history segment dependencies. For a thread without explicit ownership, infer the deepest matching project root when possible.
3. Map known structured paths using explicit longest-prefix mappings. Keep ordinary conversation text unchanged, including paths mentioned in messages. Set imported sandbox policy to read-only; recovered historical permissions should not silently authorize new execution. This does not replace normal client permission controls.
4. Reconstruct selected session files as JSONL, preserve message bytes, recalculate segment offsets and rewrite history references. Both plain and Zstandard inputs are accepted with strict frame completion checks.
5. Build an isolated merge against target snapshots. Reuse destination projects with matching ordered roots; keep destination names. Otherwise import nonconflicting native IDs. Merge only selected legacy sidebar associations instead of replacing the destination global state wholesale.
6. On apply, verify frozen preparation inputs, check mapped source directories exist and require Windows client processes to be absent. Acquire a tool-specific lock and rebuild against current target data. Compare fingerprints before installation.
7. Create standalone database snapshots and metadata backups in the destination profile. Journal intended new session files. Copy and verify each file, then replace it using a staging file within its destination directory.
8. Check installed database integrity and protected account configuration. Save the completion receipt. Reopen the client only after successful completion.

## Snapshots, sidecars and cross-volume moves

SQLite backup snapshots already contain committed WAL changes. Restoring a snapshot and then reattaching the saved old WAL can replay incompatible data; this implementation archives sidecars for diagnosis only. Rollback restores standalone snapshots.

`os.replace` cannot move a file across Windows volumes. Source/workspace files may be on another volume, so transfer uses copy, SHA-256 comparison, then same-directory replacement. Archive/removal uses copy, verify, unlink.

This is a sequence of file operations, not a transaction across every database and file. Process checks and fingerprints reduce races but do not prevent another renamed client or arbitrary writer from accessing the profile. A shutdown, disk failure, forced process kill, malicious input or manual modification can still require human intervention. Operate on trusted backups and retain an independent copy.

## Receipt states

| State | Meaning and next action |
| --- | --- |
| `prepared` | Backup created; installation has not been recorded as started. Inspect if a prior run stopped. |
| `installing` | File installation may be partial. Keep client closed; inspect backups/receipt. |
| `complete` | Installation and integrity checks finished; keep receipt before reopening. |
| `rolled_back` | Stored snapshots were restored after failure or explicit unchanged-target rollback. |
| `rollback_incomplete` | Automatic restore failed or client activity blocked safe restore. Preserve all files and seek manual review. |

The `rollback` command accepts only `complete` receipts with matching post-install target fingerprints and unchanged added files. It intentionally refuses to overwrite newer activity. Other states require inspection; do not change the receipt state manually to bypass checks.

## Version and feature limits

Compatibility is determined from SQLite definitions, migration records and `user_version`, not a marketing release number. Exact equality is deliberately conservative and may reject backups that an expert could convert manually. Accepted equality alone is not proof of semantic compatibility; inspect and test against copies first.

V0.1 expects `state_5.sqlite`, `thread_history_1.sqlite`, and `sqlite/codex-dev.db` and the table/column families exercised by the synthetic fixture. It does not upgrade old schemas. Modifying commands require Windows. Path preflight rejects managed paths of 240 characters or more rather than attempting extended path handling.

Authentication/configuration and installation ID are protected, not imported. Skills/plugins and project code are not copied. Attachment metadata can be retained, but image/external attachment binaries are outside v0.1; a recovered conversation can still contain broken images. ChatGPT cloud history is outside this tool's scope.

## Testing interpretation

Synthetic tests exercise supported relationships and observable invariants without real user data. Passing tests show the adapter behaves as specified on those fixtures; they do not demonstrate every current or future Codex storage variant. A failure should lead to a minimized synthetic reproduction and a narrow implementation change.
