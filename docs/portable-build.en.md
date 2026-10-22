# Windows portable build preparation

[中文](portable-build.md) · [Back to the project](../README.en.md)

This repository now contains a Windows x64 single-file candidate build. It bundles the Python runtime, recovery helper, engine, and Zstandard support in one EXE, so users do not need to install Python. The portable build keeps the source helper's command interface and copies its own executable into the recovery workspace for the independent launcher.

## Current status

These are build and validation instructions; they do not mean a download is published on GitHub. The current candidate is unsigned and has not been tested in a clean Windows VM. Do not treat it as an official release or use it with real personal data. Only Windows x64 is prepared; ARM64, 32-bit, and other operating systems are not packaged.

## Build

Use Windows x64 CPython 3.11+ and run from the repository root:

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv-build\Scripts\python.exe scripts\build_portable.py --allow-dirty
```

`requirements-build.txt` pins PyInstaller, the compression library, CI tools, and build dependencies. For a release candidate, use a clean Git commit and omit `--allow-dirty`. The script records the commit, whether the tree has changes, and the Python and dependency versions; by default it stops when the source tree is dirty.

The default output is under `dist/`: a candidate ZIP, a SHA-256 file for the ZIP, and an internal executable checksum list, build information, usage guide, and license texts. The script does not upload or publish these files.

## Why one file, and its limits

One file is easy to copy into a recovery workspace and run after Codex closes. PyInstaller extracts application components to a Windows temporary directory at runtime, so first launch is slower; that temporary directory may remain if the process is forcibly terminated. Single-file mode is harder to troubleshoot than a folder bundle, so it still needs clean-system testing before release.

The candidate is unsigned. Windows SmartScreen or security software may warn about an unknown publisher; a checksum can detect accidental changes but cannot prove publisher identity or code safety. A formal release should be tied to a specific commit, have its archive inspected, include trusted build provenance, and be published as an immutable GitHub Release only after human review.

## Remaining validation

- Run on clean Windows x64 without system Python or development tools on PATH.
- Inspect, prepare, and verify from paths containing Chinese characters and spaces; test compressed history with a synthetic `.jsonl.zst` session.
- Confirm the recovery workspace can copy the EXE as its independent launcher; simulate timeout and failure and check the target remains unchanged.
- In an authorized isolated test environment, verify client-exit waiting, complete apply, and rollback of a synthetic recovery.
- Review archive contents, licenses, checksum, and build provenance before separately deciding whether to create a formal release.

See the [project README](../README.en.md) and [manual guide](manual-recovery.en.md) for scope and data limits.
