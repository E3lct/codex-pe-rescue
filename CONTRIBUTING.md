# Contributing

Use synthetic data only. Do not attach real profiles, databases, conversation exports, screenshots of chats, credentials, recovery configs, receipts or logs containing personal paths/IDs. Replace any incident details with a small fictional reproduction before posting an issue.

For behavior changes, add tests demonstrating the relevant invariant or failure. Tests belong in `tests/` and create temporary synthetic profiles at runtime. Keep changes specific to the documented storage adapter; a new schema needs explicit compatibility handling and fixture coverage.

Run `python -m unittest discover -s tests -v` after installing `.[zstd]` so compressed fixtures are included. Windows is the supported write platform. Do not use a live `.codex` folder as a test target.

Document copied/adapted third-party code and its license in `PROVENANCE.md`, retain required notices, and do not add code with an incompatible license. Submissions are intended under this repository's MIT license; submit only material you may share under that license.
