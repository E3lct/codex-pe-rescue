"""Prepare the recovery engine, preview and an independent double-click launcher."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
import uuid

ENGINE_COMMIT = "7566da1f3703e1911007c7fe47ac677973a2eac5"
ENGINE_SHA256 = "bbf4f7e9b51abf441d3763f18d6d73829361a5870711d6450b7855caf3041da3"
ENGINE_URL = "https://raw.githubusercontent.com/E3lct/codex-pe-rescue/" + ENGINE_COMMIT + "/rescue.py"


def cache_home():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache"))) / "CodexPERescue"


def target_home():
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def engine_file(cache, offline=False):
    # A copied Skill works without Git or a separate repository checkout.
    parents = Path(__file__).resolve().parents
    checkout = parents[3] / "rescue.py" if len(parents) > 3 else None
    if checkout and checkout.is_file() and (checkout.parent / "pyproject.toml").is_file():
        return checkout
    destination = Path(cache) / "engines" / ENGINE_SHA256 / "rescue.py"
    if destination.is_file():
        if sha256(destination) != ENGINE_SHA256:
            raise RuntimeError("Cached engine changed; preserve it for inspection instead of executing it")
        return destination
    if offline:
        raise RuntimeError("Offline mode: no local engine. Use a checkout or prepare the cache while online")
    print("Preparing the pinned engine from the official project...", file=sys.stderr)
    with urllib.request.urlopen(ENGINE_URL, timeout=30) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != ENGINE_SHA256:
        raise RuntimeError("Downloaded engine failed SHA-256 verification; nothing was executed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    temporary.write_bytes(data)
    os.replace(temporary, destination)
    return destination


def runtime(cache, offline=False):
    environment = Path(cache) / "python-env"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        if offline:
            raise RuntimeError("Offline mode: isolated Python environment is not prepared")
        print("Preparing an isolated Python environment (no system Python changes)...", file=sys.stderr)
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    check = subprocess.run([str(python), "-c", "import zstandard"], capture_output=True)
    if check.returncode:
        if offline:
            raise RuntimeError("Offline mode: the isolated environment needs zstandard")
        subprocess.run([str(python), "-m", "pip", "install", "zstandard>=0.22,<1"],
                       check=True, stdout=sys.stderr)
    return python.resolve()


def run_engine(python, engine, arguments):
    result = subprocess.run([str(python), str(engine), *map(str, arguments)],
                            capture_output=True, text=True, encoding="utf-8",
                            env=dict(os.environ, PYTHONUTF8="1"))
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Recovery engine failed")
    return json.loads(result.stdout)


def batch_arg(value):
    value = str(value)
    if any(c in value for c in ('"', "\r", "\n", "\0")):
        raise RuntimeError("Cannot represent this path in a Windows launcher")
    return '"' + value.replace("%", "%%") + '"'


def prepare_recovery(source, target, project_ids, thread_ids, mappings, workspace,
                     python, engine, cache):
    workspace, cache = [Path(p).expanduser().resolve() for p in (workspace, cache)]
    if workspace.exists():
        raise RuntimeError("Choose a new workspace; existing work is not overwritten")
    for value in (python, workspace / "run-recovery.py", workspace):
        batch_arg(value)
    config = {"source_home": str(Path(source).expanduser().resolve()),
              "target_home": str(Path(target).expanduser().resolve()),
              "project_ids": project_ids, "thread_ids": thread_ids, "path_map": dict(mappings)}
    if len(config["path_map"]) != len(mappings):
        raise RuntimeError("Repeated old path mappings; use one destination for each old path")
    frozen_engine = cache / "engines" / sha256(engine) / "rescue.py"
    frozen_engine.parent.mkdir(parents=True, exist_ok=True)
    if frozen_engine.resolve() != Path(engine).resolve():
        if frozen_engine.exists() and sha256(frozen_engine) != sha256(engine):
            raise RuntimeError("Frozen engine cache is conflicting")
        shutil.copy2(engine, frozen_engine)
    config_file = cache / "requests" / (uuid.uuid4().hex + ".json")
    save(config_file, config)
    report = run_engine(python, frozen_engine, ["prepare", "--config", config_file, "--workspace", workspace])
    run_engine(python, frozen_engine, ["verify", "--workspace", workspace])
    helper = workspace / "run-recovery.py"
    shutil.copy2(__file__, helper)
    save(workspace / "handoff.json", {"workspace": str(workspace), "python": str(python),
                                      "engine": str(frozen_engine), "engine_sha256": sha256(frozen_engine)})
    launcher = workspace / "Start-Recovery.cmd"
    command = " ".join([batch_arg(python), batch_arg(helper), "wait", "--workspace", batch_arg(workspace)])
    launcher.write_text("@echo off\r\nchcp 65001 >nul\r\nsetlocal DisableDelayedExpansion\r\n" + command +
                        "\r\nset rescue_exit=%errorlevel%\r\necho.\r\npause\r\nexit /b %rescue_exit%\r\n",
                        encoding="utf-8", newline="")
    summary = {"state": "preview_ready", "workspace": str(workspace), "launcher": str(launcher),
               "preview": str(workspace / "preview.json"), "report": report,
               "next": "Review preview. Double-click launcher, then fully exit Codex. It waits 10 quiet seconds."}
    save(workspace / "assistant-summary.json", summary)
    save(cache / "latest.json", {"workspace": str(workspace)})
    return summary


def wait_for_closed(guard, quiet_seconds=10, timeout=1800, clock=time.monotonic, sleep=time.sleep):
    started = clock()
    quiet_since = None
    last_message = None
    while True:
        now = clock()
        try:
            guard()
        except RuntimeError as error:
            if not str(error).startswith("Close Codex/ChatGPT"):
                raise
            quiet_since = None
            message = str(error)
            if message != last_message:
                print("Waiting for Codex to fully exit. " + message, flush=True)
            last_message = message
        else:
            if quiet_since is None:
                quiet_since = now
                print("Client exited. Confirming 10 quiet seconds before backup and recovery...", flush=True)
            if now - quiet_since >= quiet_seconds:
                return
        if now - started >= timeout:
            raise TimeoutError("Wait timed out; no recovery was installed. Close the client and run the launcher again")
        sleep(1)


def load_engine(path):
    spec = importlib.util.spec_from_file_location("pe_rescue_engine", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_and_apply(workspace, timeout=1800):
    workspace = Path(workspace).resolve()
    if (workspace / "result.json").is_file():
        previous = read(workspace / "result.json")
        if previous.get("state") == "complete":
            print("Previous recovery completed; no new write. Receipt: " + previous["receipt"], flush=True)
            return previous
        if previous.get("state") == "failed":
            raise RuntimeError("Previous run failed; inspect its saved error and backups before preparing a new operation")
    try:
        handoff = read(workspace / "handoff.json")
        if Path(handoff["workspace"]).resolve() != workspace:
            raise RuntimeError("Workspace moved; prepare a new plan instead of changing the handoff")
        if sha256(handoff["engine"]) != handoff["engine_sha256"]:
            raise RuntimeError("Prepared engine changed; no recovery was installed")
        engine = load_engine(handoff["engine"])
        engine.verify(workspace)
        print("Recovery launcher is ready. Keep this window open and fully exit Codex.", flush=True)
        wait_for_closed(engine.require_windows_closed, timeout=timeout)
        print("Backing up and installing selected history. Do not reopen Codex yet...", flush=True)
        result = engine.apply(workspace)
        save(workspace / "result.json", result)
        print("RECOVERY COMPLETE. You may reopen Codex. Receipt: " + result["receipt"], flush=True)
        return result
    except Exception as error:
        save(workspace / "result.json", {"state": "waiting_timeout" if isinstance(error, TimeoutError)
                                         else "failed", "error": str(error)})
        (workspace / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        print("RECOVERY NOT COMPLETED: " + str(error), file=sys.stderr, flush=True)
        print("Keep source, workspace and backups. A partial install needs review before reopening.",
              file=sys.stderr, flush=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=cache_home())
    parser.add_argument("--offline", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="Automatically prepare engine and isolated dependencies")
    inspect = commands.add_parser("inspect", help="List projects/chats; optionally filter titles and paths")
    inspect.add_argument("--source-home", required=True, type=Path)
    inspect.add_argument("--query", default="")
    prepare = commands.add_parser("prepare", help="Create config, preview and a double-click launcher")
    prepare.add_argument("--source-home", required=True, type=Path)
    prepare.add_argument("--target-home", type=Path, default=target_home())
    prepare.add_argument("--project-id", action="append", default=[])
    prepare.add_argument("--thread-id", action="append", default=[])
    prepare.add_argument("--map", nargs=2, action="append", default=[], metavar=("OLD", "NEW"))
    prepare.add_argument("--workspace", type=Path)
    wait = commands.add_parser("wait", help="Wait for client exit, then install the prepared plan")
    wait.add_argument("--workspace", type=Path, required=True)
    wait.add_argument("--timeout", type=int, default=1800)
    status = commands.add_parser("status", help="Read the saved outcome of the latest operation")
    status.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "wait":
            result = wait_and_apply(args.workspace, args.timeout)
        elif args.command == "status":
            workspace = args.workspace or Path(read(args.cache / "latest.json")["workspace"])
            result = read(workspace / "assistant-summary.json")
            result["outcome"] = read(workspace / "result.json") if (workspace / "result.json").is_file() else None
        else:
            if args.command in ("inspect", "prepare"):
                cache = args.cache.expanduser().resolve()
                for home in (args.source_home, getattr(args, "target_home", target_home())):
                    home = home.expanduser().resolve()
                    if cache.is_relative_to(home) or home.is_relative_to(cache):
                        raise RuntimeError("Tool cache must be separate from both source and target profiles")
            engine = engine_file(args.cache, args.offline)
            if args.command == "inspect":
                result = run_engine(sys.executable, engine, ["inspect", "--source-home", args.source_home])
                if args.query:
                    query = args.query.casefold()
                    result["projects"] = [p for p in result["projects"] if query in
                                           (p.get("name", "") + " " + " ".join(p["roots"])).casefold()]
                    result["threads"] = [t for t in result["threads"] if query in
                                          ((t.get("title") or "") + " " + (t.get("cwd") or "")).casefold()]
            else:
                python = runtime(args.cache, args.offline)
                if args.command == "setup":
                    result = {"ready": True, "engine": str(engine), "python": str(python), "cache": str(args.cache)}
                else:
                    workspace = args.workspace or args.cache / "runs" / uuid.uuid4().hex[:8]
                    result = prepare_recovery(args.source_home, args.target_home, args.project_id,
                                              args.thread_id, args.map, workspace, python, engine, args.cache)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11+ required. Use an available Codex runtime or python.org")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
