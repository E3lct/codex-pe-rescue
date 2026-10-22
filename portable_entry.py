"""Windows portable executable entry point for the guided recovery helper."""
from __future__ import annotations

import sys
from pathlib import Path
import importlib.util

import rescue

if getattr(sys, "frozen", False):
    assist_path = Path(sys._MEIPASS) / "assist.py"
else:
    assist_path = (Path(__file__).resolve().parent / "skills" / "codex-pe-rescue" /
                   "scripts" / "assist.py")
spec = importlib.util.spec_from_file_location("codex_pe_rescue_assist", assist_path)
assist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assist)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = sys.argv[1:]
    if arguments[:1] == ["--_engine"]:
        return rescue.main(arguments[1:])
    return assist.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
