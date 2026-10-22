# Assistant workflow and commands

`<python>` means a verified Python 3.11+ executable; `<helper>` is the absolute path to this Skill's `scripts/assist.py`. Resolve both yourself. Use argument arrays or proper shell quoting. The placeholders below are instructions for the assistant, not work to give to the user.

## Minimal intake

Reuse paths and authorization already supplied. If only the backup is unknown, ask: “旧 `.codex` 备份在哪个文件夹？” If several chats match, show a small selection of titles and ask which one. If roots moved, show the old root and plausible new folders and ask only for the correspondence. Map answers to IDs yourself. Do not ask the user to write JSON or decide database details.

Do not ask every possible question up front: files may answer them. Do not import everything when one chat was requested.

Use a structured question tool if the host provides one; otherwise use short numbered options. Initial unknown-material options are raw `.codex` backup / existing `.rehome` package / unsure. For unknown scope offer inspect the list / selected projects / one chat. Skip either question when already answered. Ask for new-path correspondences only after discovering the old roots and checking candidate destinations. The repository's `docs/guided-recovery-flow.md` contains the complete flow; installed Skills can follow these essentials without a checkout.

## Inspect

```text
<python> <helper> inspect --source-home <offline-backup>
<python> <helper> inspect --source-home <offline-backup> --query <topic-or-folder>
```

This finds an adjacent engine or downloads a pinned, hash-checked copy from `E3lct/codex-pe-rescue`. It needs no dependency installation and does not edit the destination. The filter searches titles and paths, not message bodies. If needed, inspect relevant session text locally within scope; do not promise full-text search from this filter. Project name and chat subject can differ.

Target must be an initialized Codex installation with compatible native project/history/catalog databases. If missing, explain that the user needs to open/sign in to Codex normally once; do not copy old credentials.

## Prepare automatically

```text
<python> <helper> prepare --source-home <backup> --project-id <id-from-inspect> --map <old-root> <new-root>
```

Use `--thread-id` for a single chat. Repeat options for multiple entries. `--target-home` overrides `CODEX_HOME` / current user's `.codex`. `--workspace` overrides the private auto-created location. Unchanged roots still need identity mappings. Actual project source directories must already exist.

Preparation creates an isolated user-cache Python environment and installs `zstandard` there to read compressed chat history. It does not change global Python, PATH, registry or services. The helper downloads the pinned recovery engine from GitHub and the library from the configured Python package repository; these are software downloads, and the helper does not upload recovery data. Local inspection may return private titles or paths to the assistant, which the AI platform handles under its own policies. `--offline` before the subcommand requires cached components and performs no installation/download. `setup` can pre-cache explicitly.

Read the returned report and plan yourself. Present the selection, mapped roots, existing-history preservation and attachment limitation in plain language. Ask for approval only when required by the user's rules, after the concrete preview exists. Keep configs, previews and logs out of the public checkout.

## Independent launch

Link the returned absolute `launcher` path (`Start-Recovery.cmd`) for the user to double-click. If authorized, open it in an independent visible terminal using properly quoted native process-launch arguments. It must survive closing Codex. Do not wait in the current Codex terminal, run a hidden task, kill clients or use a scheduled job.

Tell the user: double-click first, keep the window open, fully exit Codex, wait for `RECOVERY COMPLETE`, then reopen. The runner waits up to 30 minutes, requires 10 quiet seconds and repeats engine guards during writes. It uses the exact frozen engine/interpreter, saves `result.json`, and pauses after success/failure. A failure also saves private `failure.log`. A waiting timeout starts no install and permits a later rerun after client exit.

## Verify after reopening

```text
<python> <helper> status
<python> <helper> status --workspace <operation-directory>
```

The default reads the latest-operation pointer in the private cache. `outcome: null` is not success. `waiting_timeout` means installation did not start. `failed` requires inspecting the error and engine receipt to distinguish automatic rollback from partial installation. Do not advise reopening after a partial install.

For rollback details and failure states, consult the [manual recovery guide](https://github.com/E3lct/codex-pe-rescue/blob/main/docs/manual-recovery.md) and [recovery model](https://github.com/E3lct/codex-pe-rescue/blob/main/docs/recovery-model.md), or the corresponding files in an available checkout. The guarded engine command is `rollback --receipt <returned-path> --yes --codex-stopped` from an independent terminal. It requires an unchanged completed target. Do not bypass rejection after newer activity or replay saved WAL onto standalone snapshots.
