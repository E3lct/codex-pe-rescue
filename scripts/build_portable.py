"""Build an auditable Windows x64 portable candidate ZIP."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
PYINSTALLER_VERSION = "6.22.3"
ZSTANDARD_VERSION = "0.25.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_state() -> tuple[str, bool]:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            check=True, capture_output=True, text=True).stdout.strip()
    changed = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"],
                             cwd=ROOT, check=True, capture_output=True, text=True).stdout
    return commit, bool(changed.strip())


def pinned_requirements(path: Path | None = None, result: dict[str, str] | None = None) -> dict[str, str]:
    path = ROOT / "requirements-build.txt" if path is None else path
    result = {} if result is None else result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            included = (path.parent / line[3:].strip()).resolve()
            if not included.is_relative_to(ROOT.resolve()):
                raise RuntimeError("Nested build requirement files must remain inside the repository")
            pinned_requirements(included, result)
            continue
        name, separator, version = line.partition("==")
        if not separator or not name or not version:
            raise RuntimeError("Every build dependency must use an exact == pin")
        result[name.lower().replace("_", "-")] = version
    return result


def check_build_environment() -> dict[str, str]:
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Portable releases are currently built only on Windows x64")
    if sys.version_info < (3, 11):
        raise RuntimeError("Build CPython 3.11 or newer")
    installed = pinned_requirements()
    expected = {
        "pip": "26.2.2",
        "setuptools": "84.2.1",
        "zstandard": ZSTANDARD_VERSION,
        "altgraph": "0.17.5",
        "packaging": "26.3",
        "pefile": "2024.8.26",
        "pyinstaller": PYINSTALLER_VERSION,
        "pyinstaller-hooks-contrib": "2026.9",
        "pywin32-ctypes": "0.2.3",
    }
    if installed != expected:
        raise RuntimeError("requirements-build.txt pins changed; review the build script's expected versions")
    for name, version in expected.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise RuntimeError(f"Missing build dependency: {name}=={version}") from error
        if actual != version:
            raise RuntimeError(f"Expected {name}=={version}, found {actual}")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("The active CPython installation has no LICENSE.txt to include")
    return expected


def license_from_distribution(name: str, suffix: str) -> Path:
    distribution = importlib.metadata.distribution(name)
    for member in distribution.files or ():
        if str(member).replace("\\", "/").endswith(suffix):
            path = Path(distribution.locate_file(member))
            if path.is_file():
                return path
    raise RuntimeError(f"Required license file not found in {name}: {suffix}")


def copy_license(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise RuntimeError(f"Required license file is missing: {source.name}")
    shutil.copyfile(source, destination)


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def build(args: argparse.Namespace) -> Path:
    versions = check_build_environment()
    commit, dirty = git_state()
    if dirty and not args.allow_dirty:
        raise RuntimeError("The working tree has changes; inspect them or pass --allow-dirty for a local candidate")

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    artifact_name = f"codex-pe-rescue-v{version}-windows-x64-candidate"
    DIST_DIR.mkdir(exist_ok=True)
    output = (Path(args.output).resolve() if args.output else DIST_DIR / f"{artifact_name}.zip")
    if not output.resolve().is_relative_to(DIST_DIR.resolve()):
        raise RuntimeError("Output must stay inside the repository's ignored dist/ directory")
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    if output.exists() or checksum_path.exists():
        raise FileExistsError("Refusing to overwrite an existing candidate ZIP or checksum")

    BUILD_DIR.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="portable-candidate-", dir=BUILD_DIR))
    try:
        frozen_dist = work / "frozen"
        command = [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--onefile", "--console", "--name", "codex-pe-rescue",
            "--distpath", str(frozen_dist), "--workpath", str(work / "pyinstaller-work"),
            "--specpath", str(work / "spec"),
            "--add-data", f"{ROOT / 'rescue.py'};. ".strip(),
            "--add-data", f"{ROOT / 'skills/codex-pe-rescue/scripts/assist.py'};. ".strip(),
            "--collect-all", "zstandard",
            "--hidden-import", "argparse", "--hidden-import", "hashlib",
            "--hidden-import", "importlib.util", "--hidden-import", "json",
            "--hidden-import", "os", "--hidden-import", "pathlib",
            "--hidden-import", "shutil", "--hidden-import", "subprocess",
            "--hidden-import", "sys", "--hidden-import", "time",
            "--hidden-import", "traceback", "--hidden-import", "urllib.request",
            "--hidden-import", "uuid", "--hidden-import", "zstandard.backend_c",
            str(ROOT / "portable_entry.py"),
        ]
        run(command)
        executable = frozen_dist / "codex-pe-rescue.exe"
        if not executable.is_file() or executable.stat().st_size < 5 * 1024 * 1024:
            raise RuntimeError("PyInstaller did not produce the expected self-contained Windows executable")

        staging = work / artifact_name
        staging.mkdir()
        shutil.copy2(executable, staging / executable.name)
        shutil.copy2(ROOT / "LICENSE", staging / "LICENSE")
        shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", staging / "THIRD_PARTY_NOTICES.md")
        shutil.copy2(ROOT / "docs/portable-user-guide.md", staging / "PORTABLE-README.md")
        licenses = staging / "licenses"
        licenses.mkdir()
        copy_license(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
        copy_license(license_from_distribution("zstandard", "licenses/LICENSE"),
                     licenses / "python-zstandard-LICENSE.txt")
        copy_license(ROOT / "licenses/zstd-LICENSE.txt", licenses / "Zstandard-LICENSE.txt")
        copy_license(license_from_distribution("pyinstaller", "licenses/COPYING.txt"),
                     licenses / "PyInstaller-COPYING.txt")

        build_info = (
            f"Project version: {version}\n"
            f"Source commit: {commit}\n"
            f"Source tree has uncommitted changes: {'yes' if dirty else 'no'}\n"
            f"Target: Windows x64\n"
            f"Build Python: {platform.python_version()} ({platform.python_implementation()})\n"
            f"PyInstaller: {versions['pyinstaller']}\n"
            f"python-zstandard: {versions['zstandard']}\n"
            "Release state: local candidate; not a published or signed release\n"
        )
        (staging / "BUILD-INFO.txt").write_text(build_info, encoding="utf-8", newline="\n")
        executable_hash = sha256(staging / executable.name)
        (staging / "SHA256SUMS.txt").write_text(
            f"{executable_hash}  {executable.name}\n", encoding="ascii", newline="\n")

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    relative = Path(artifact_name) / path.relative_to(staging)
                    info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED,
                                     compresslevel=9)
        archive_hash = sha256(output)
        checksum_path.write_text(f"{archive_hash}  {output.name}\n", encoding="ascii", newline="\n")
        smoke(output, work)
        run([sys.executable, str(ROOT / "tests/portable_smoke.py"), str(output)])
        print(f"Portable candidate: {output}")
        print(f"SHA-256: {checksum_path}")
        return output
    finally:
        resolved_work = work.resolve()
        resolved_build = BUILD_DIR.resolve()
        if resolved_work.parent == resolved_build and resolved_work.name.startswith("portable-candidate-"):
            shutil.rmtree(resolved_work)


def smoke(archive: Path, work: Path) -> None:
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX"):
        environment.pop(key, None)
    system_root = Path(environment.get("SystemRoot", r"C:\Windows"))
    environment["PATH"] = os.pathsep.join((str(system_root / "System32"), str(system_root)))
    with zipfile.ZipFile(archive) as bundle:
        exe_name = next(name for name in bundle.namelist() if name.endswith("/codex-pe-rescue.exe"))
        executable = work / "codex-pe-rescue.exe"
        executable.write_bytes(bundle.read(exe_name))
    for arguments, expected in ((["--help"], "usage:"), (["--_engine", "--version"], "0.1.0")):
        result = subprocess.run([str(executable), *arguments], cwd=work, env=environment,
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
        if result.returncode != 0 or expected not in result.stdout:
            raise RuntimeError(f"Portable executable smoke test failed for {arguments}: {result.stderr.strip()}")
    cache = work / "offline cache with spaces"
    result = subprocess.run([str(executable), "--offline", "--cache", str(cache), "setup"],
                            cwd=work, env=environment, capture_output=True, text=True,
                            encoding="utf-8", timeout=60)
    if result.returncode != 0 or '"ready": true' not in result.stdout:
        raise RuntimeError("Portable offline setup smoke test failed: " + result.stderr.strip())
    if cache.exists():
        raise RuntimeError("Portable setup unexpectedly created a Python environment or cache files")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-dirty", action="store_true",
                        help="Build a local candidate from uncommitted source changes")
    parser.add_argument("--output", type=Path,
                        help="Candidate ZIP path inside dist/ (must not already exist)")
    args = parser.parse_args()
    try:
        build(args)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError, StopIteration,
            importlib.metadata.PackageNotFoundError, KeyError, ValueError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
