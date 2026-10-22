# Codex PE Rescue

[中文](README.md) · [License](LICENSE) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

Can your old Windows system no longer boot, leaving only a raw `.codex` backup copied with recovery media? This tool helps select local Codex projects and chats from that backup, merge them into a new installation, and map old project paths to their new locations. Project source files must be backed up and restored separately.

Use it after reinstalling Windows or relocating local Codex data. It prepares a merge preview before writing a backed-up recovery while the client is closed. The old system does not need to export a migration package first.

## Safety and scope

- Recovery data is processed locally and is not uploaded by the tool. Initial setup downloads a pinned engine from GitHub and installs dependencies from a Python package index. How an AI platform handles prompts and tool results depends on that platform.
- Backups, inspection output, workspaces, and receipts may contain private chats or paths. Keep them outside the repository and do not publish them.
- The tool does not restore ChatGPT cloud history, project source files, account credentials, old skills/plugins, or image/external attachment binaries. Images in recovered chats may remain unavailable.
- **Experimental v0.1.0, Windows write adapter.** It depends on an unpublished, changing local data format. It is not an official OpenAI import tool and is not guaranteed to work with every version.
- Source and destination schemas, migration records, and `user_version` must match. The tool stops when they do not. Older JSON-only project registries and database-version conversion are unsupported.

## Quick start: AI-guided recovery

Give this repository link to an assistant that can access local files and run commands, and ask it to recover your old Codex projects or chats. The [repository AI guide](AGENTS.md) and [recovery Skill](skills/codex-pe-rescue/SKILL.md) point to the workflow; whether an AI automatically reads these files depends on its platform.

The assistant inspects the backup and prepares a preview. It asks only when it cannot determine the backup location, chat selection, or old-to-new folder mapping. You do not need to enter database IDs or write JSON. Before installation, fully exit Codex and use the generated standalone launcher; then reopen Codex and verify the sidebar and chats.

Python 3.11+ must be available. A regular web chat without local file access can only provide instructions. See the [assistant workflow](skills/codex-pe-rescue/references/assistant-workflow.md). Installing the Skill is optional.

## Manual recovery

If you prefer to run the commands yourself, follow the [manual recovery guide](docs/manual-recovery.en.md). The full sequence is: inspect the backup, select projects or chats, map paths, review the preview, exit the client before applying, and verify the result.

## Development and help

- [Recovery model and failure states](docs/recovery-model.md) · [Guided workflow design](docs/guided-recovery-flow.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Provenance and dependencies](PROVENANCE.md) · [MIT License](LICENSE)
- Synthetic test commands and manual operations are in the [manual recovery guide](docs/manual-recovery.en.md). For reports, share only sanitized descriptions or synthetic examples. Do not attach real backups, chats, databases, credentials, or private paths.

The current source requires Python 3.11+; modifying commands run only on Windows. A portable build with its own Python runtime has not been released. Project paths are runtime inputs, so different paths do not require code changes or a rebuild.
