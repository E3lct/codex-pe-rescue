# Portable candidate: quick use

This local build candidate is not an official release. Do not use it with real personal data before the release review and clean-system validation are complete.

The EXE is a command-line tool intended for an AI assistant or an operator who can run commands. It is not a graphical app. The project supports Windows x64 only. The candidate contains Python and compressed-history support, and does not need a separate Python install or network access to prepare its engine.

Use `codex-pe-rescue.exe --help` to view commands. The guided workflow is `inspect`, `prepare`, then double-click the generated `Start-Recovery.cmd` after reviewing the preview. The launcher waits for Codex to exit and records the final result in the private workspace. Keep backups, workspaces, previews, and receipts on the local machine.

Read the repository's manual recovery guide for selection and rollback limits. The tool does not restore project source files, credentials, images, attachments, ChatGPT cloud history, skills, or plugins. Preserve the original offline backup.
