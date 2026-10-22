"""Exercise a built portable candidate with synthetic compressed profiles."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import test_rescue as fixtures


def main() -> int:
    archive = Path(sys.argv[1]).resolve()
    root = Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(archive) as bundle:
        executable_member = next(
            (name for name in bundle.namelist() if name.endswith("/codex-pe-rescue.exe")),
            None,
        )
        if executable_member is None:
            raise RuntimeError("Candidate archive does not contain codex-pe-rescue.exe")
        prefix = executable_member.rsplit("/", 1)[0] + "/"
        required = {
            executable_member,
            prefix + "PORTABLE-README.md",
            prefix + "THIRD_PARTY_NOTICES.md",
            prefix + "licenses/Python-LICENSE.txt",
            prefix + "licenses/python-zstandard-LICENSE.txt",
            prefix + "licenses/Zstandard-LICENSE.txt",
            prefix + "licenses/PyInstaller-COPYING.txt",
        }
        missing = required - set(bundle.namelist())
        if missing:
            raise RuntimeError("Candidate archive is missing required files: " + ", ".join(sorted(missing)))
        executable_bytes = bundle.read(executable_member)

    build_dir = root / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    parent = Path(tempfile.mkdtemp(prefix="portable-smoke-中文-", dir=build_dir))
    old_tempdir = tempfile.tempdir
    tempfile.tempdir = str(parent)
    case = fixtures.CompressedTests(methodName="test_concatenated_zstd_frames_are_supported")
    try:
        case.setUp()
        # Use two Zstandard frames to cover the decoder path in the packaged runtime.
        import zstandard
        raw = zstandard.ZstdDecompressor().decompress(case.base.read_bytes())
        middle = raw.index(b"\n") + 1
        case.base.write_bytes(zstandard.ZstdCompressor().compress(raw[:middle]) +
                              zstandard.ZstdCompressor().compress(raw[middle:]))

        executable = case.root / "portable candidate.exe"
        executable.write_bytes(executable_bytes)
        environment = os.environ.copy()
        for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX"):
            environment.pop(key, None)
        system_root = Path(environment.get("SystemRoot", r"C:\Windows"))
        environment["PATH"] = os.pathsep.join((str(system_root / "System32"), str(system_root)))
        cache = case.root / "私有缓存 with spaces"

        inspected = subprocess.run(
            [str(executable), "--offline", "--cache", str(cache), "inspect",
             "--source-home", str(case.source)], cwd=case.root, env=environment,
            capture_output=True, text=True, encoding="utf-8", timeout=60)
        if inspected.returncode:
            raise RuntimeError("Packaged inspect failed: " + inspected.stderr.strip())
        inventory = json.loads(inspected.stdout)
        if not any(row.get("id") == "source-project" for row in inventory["projects"]):
            raise RuntimeError("Packaged inspect did not find the synthetic project")

        workspace = case.root / "恢复工作区 with spaces"
        prepared = subprocess.run(
            [str(executable), "--offline", "--cache", str(cache), "prepare",
             "--source-home", str(case.source), "--target-home", str(case.target),
             "--project-id", "source-project", "--map", fixtures.OLD_ROOT, str(case.project),
             "--workspace", str(workspace)], cwd=case.root, env=environment,
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        if prepared.returncode:
            raise RuntimeError("Packaged prepare failed: " + prepared.stderr.strip())
        summary = json.loads(prepared.stdout)
        if summary["state"] != "preview_ready" or summary["report"]["segments"] != 2:
            raise RuntimeError("Packaged prepare did not verify both compressed session segments")
        if (workspace / "run-recovery.exe").read_bytes() != executable_bytes:
            raise RuntimeError("Prepared handoff did not copy the portable executable")
        target_before = fixtures.bytes_tree(case.target)

        waiting = subprocess.run(
            [str(workspace / "run-recovery.exe"), "wait", "--workspace", str(workspace),
             "--timeout", "0"], cwd=case.root, env=environment,
            capture_output=True, text=True, encoding="utf-8", timeout=60)
        outcome = json.loads((workspace / "result.json").read_text(encoding="utf-8"))
        if waiting.returncode == 0 or outcome.get("state") != "waiting_timeout":
            raise RuntimeError("Packaged independent launcher did not record a safe waiting timeout")
        if fixtures.bytes_tree(case.target) != target_before:
            raise RuntimeError("Timed-out portable launcher changed the synthetic target")
        if (cache / "python-env").exists():
            raise RuntimeError("Portable build unexpectedly created an isolated Python environment")
        print("Portable integration smoke passed: offline inspect, compressed prepare, copied EXE, safe timeout.")
        return 0
    finally:
        case.doCleanups()
        tempfile.tempdir = old_tempdir
        parent.rmdir()


if __name__ == "__main__":
    raise SystemExit(main())
