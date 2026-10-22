# Security and private data

This tool writes local application records. Use a preserved offline backup and keep a separate copy before experimenting. Prepared workspaces and rollback backups contain private conversation data even when their file names look generic. Do not publish them.

The core engine performs local file/database operations and does not call a network service. The assistant helper downloads a pinned engine from GitHub with SHA-256 verification and installs `zstandard` from the configured Python package repository into an isolated user-cache environment. These requests download software; the helper does not upload recovery data. Local inspection may return chat titles, project names, or paths to the assistant, and the AI platform handles prompts and tool results under its own policies. Review source changes before running a version you do not trust. Hash manifests detect accidental changes to prepared data; they are not a signature or protection against an attacker controlling both manifest and payload.

Account authentication/configuration is not imported. Process checks, target fingerprints and rollback guards are conservative safeguards, not isolation from arbitrary external writers. Stop on a partial-install report and preserve the evidence locally.

For public reports, provide only a sanitized description or a synthetic reproduction. Do not post tokens, real chats, database files or personally identifying paths. This repository does not promise a private vulnerability intake channel or response time. If a report cannot be shared safely, do not put sensitive details in a public issue.
