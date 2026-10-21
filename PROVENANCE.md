# Provenance and related work

## This implementation

This repository contains newly authored, AI-assisted Python code. Its starting point was a one-off local recovery procedure after an unbootable Windows installation. The public implementation was rewritten with explicit inputs, synthetic fixtures, compatibility checks, selective merging and recoverable file installation. The original private scripts, profiles, logs and incident-specific identifiers are not included.

The repository does not vendor source files from the projects below. It is not a fork, compatibility layer, or endorsement of them. Related projects were consulted to understand recovery/migration approaches; that does not establish identical behavior or a comparative reliability claim.

## Related project

- [CalebYcj/codex-rehome](https://github.com/CalebYcj/codex-rehome): related Codex relocation/migration tooling, [MIT license](https://github.com/CalebYcj/codex-rehome/blob/main/LICENSE), copyright 2026 CalebYcj. No ReHome source code is incorporated here. If future contributions copy or adapt its code, retain the applicable copyright and license notices and identify the reused files.

## Dependencies and notices

- Python and its standard library are provided by the user's interpreter, not bundled here. See the [Python license](https://docs.python.org/3/license.html).
- Optional [`zstandard`](https://github.com/indygreg/python-zstandard) is downloaded separately to read `.jsonl.zst` records. It is not vendored in this repository. The package's wrapper code is [BSD-3-Clause licensed](https://github.com/indygreg/python-zstandard/blob/main/LICENSE), copyright 2016 Gregory Szorc; consult its package notices for bundled components. Redistribution of wheels or a future executable must preserve the notices applicable to those distributed components.
- Setuptools is a separate build dependency; it is not included in the source tree.

The project's MIT license covers this project's code and documentation. It does not relicense dependencies, Codex, recovered conversations, attachments, third-party project source, or user credentials.

Future contributions must document actual code reuse, its source and applicable notices here. Design references should be described as references, not as copied code.
