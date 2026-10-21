"""Offline-profile recovery, not an official Codex import API. See README."""
from __future__ import annotations

import argparse
import bisect
import contextlib
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid

VERSION = "0.1.0"
DATABASES = ("state_5.sqlite", "thread_history_1.sqlite", "sqlite/codex-dev.db")
METADATA = (".codex-global-state.json", ".codex-global-state.json.bak", "session_index.jsonl")
MANAGED = DATABASES + METADATA
PROTECTED = ("auth.json", "config.toml", "installation_id")
HISTORY_TABLES = ("thread_turns", "thread_items", "thread_history_projection_state",
                  "thread_realtime_items")
RELATED_TABLES = ("thread_dynamic_tools", "thread_attachments", "thread_read_receipts")
UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
MAX_EVENT = 64 * 1024 * 1024


class RescueError(RuntimeError):
    pass


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def connect(path, readonly=False):
    uri = Path(path).resolve().as_uri() + ("?mode=ro" if readonly else "")
    db = sqlite3.connect(uri, uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def check_db(db):
    if [row[0] for row in db.execute("PRAGMA quick_check")] != ["ok"]:
        raise RescueError("SQLite integrity check failed")
    if list(db.execute("PRAGMA foreign_key_check")):
        raise RescueError("SQLite foreign-key check failed")


def snapshot(source, destination):
    """Produce a standalone snapshot. Never reattach WAL to this snapshot."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()

    def progress(status, remaining, total):
        if time.monotonic() - start > 120:
            raise RescueError("SQLite snapshot timed out")

    with contextlib.closing(connect(source, True)) as original:
        with contextlib.closing(sqlite3.connect(destination)) as target:
            original.backup(target, pages=1024, progress=progress, sleep=0.01)
            target.execute("PRAGMA journal_mode=DELETE")
            target.commit()
            check_db(target)


def contained(a, b):
    return Path(a).resolve().is_relative_to(Path(b).resolve())


def member(root, relative):
    """Reject traversal, symlinks and Windows junctions in managed paths."""
    root = Path(root).resolve()
    rel = PurePosixPath(str(relative).replace("\\", "/"))
    if rel.is_absolute() or any(part in ("..", "") for part in rel.parts):
        raise RescueError("Unsafe relative path: " + str(relative))
    if any(":" in part for part in rel.parts):
        raise RescueError("Drive/stream path is not a relative file")
    path = root.joinpath(*rel.parts)
    if sys.platform == "win32" and len(str(path)) >= 240:
        raise RescueError("Path is too long for this Windows adapter; use a shorter backup/workspace path")
    for parent in [root, *list(path.parents)[:-1], path]:
        if parent.exists() and (parent.is_symlink() or
                               getattr(parent, "is_junction", lambda: False)()):
            raise RescueError("Linked managed path is not supported: " + str(parent))
    if not path.resolve().is_relative_to(root):
        raise RescueError("Managed path escapes its home")
    return path


def fingerprint(home, names=MANAGED + PROTECTED):
    result = {}
    for name in names:
        path = member(home, name)
        result[name] = digest(path) if path.is_file() else None
    for name in DATABASES:
        path = member(home, name + "-wal")
        # SHM is coordination state; SQLite readers themselves can change it.
        result[name + "-wal"] = digest(path) if path.is_file() and path.stat().st_size > 32 else None
    return result


def capture_source(source, destination, databases=DATABASES):
    """Copy DB + sidecars before opening SQLite; original PE backup is not opened."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    names = tuple(databases) + METADATA
    before = fingerprint(source, names)
    with tempfile.TemporaryDirectory(prefix="raw-", dir=destination) as temp:
        for name in databases:
            for suffix in ("", "-wal", "-shm"):
                src = member(source, name + suffix)
                dst = member(temp, name + suffix)
                if suffix == "" and not src.is_file():
                    raise RescueError("Required backup database missing: " + name)
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            snapshot(member(temp, name), member(destination, name))
    for name in METADATA:
        src = member(source, name)
        if src.is_file():
            shutil.copy2(src, member(destination, name))
    if fingerprint(source, names) != before:
        raise RescueError("Source backup changed during capture; use an offline copy")
    return before


def tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def columns(db, table):
    return [row[1] for row in db.execute("PRAGMA table_info(" + quote(table) + ")")]


def schema(db):
    definitions = [tuple(row) for row in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
    migrations = []
    if "_sqlx_migrations" in tables(db):
        fields = [x for x in ("version", "checksum", "success")
                  if x in columns(db, "_sqlx_migrations")]
        migrations = [tuple(row) for row in db.execute(
            "SELECT " + ",".join(map(quote, fields)) + " FROM _sqlx_migrations ORDER BY version")]
    return definitions, migrations, db.execute("PRAGMA user_version").fetchone()[0]


def require_schema(source, target):
    if schema(source) != schema(target):
        raise RescueError("Database schemas/migration records differ; automatic conversion is unsupported")


def insert(db, table, row):
    fields = list(row)
    db.execute("INSERT INTO " + quote(table) + " (" + ",".join(map(quote, fields)) +
               ") VALUES (" + ",".join("?" for _ in fields) + ")", tuple(row.values()))


def pure(value):
    value = str(value)
    if value.startswith("\\\\?\\"):
        value = value[4:]
    return PureWindowsPath(value) if re.match(r"^[A-Za-z]:[\\/]|^\\\\", value) else PurePosixPath(value)


def path_key(value):
    p = pure(value)
    return str(p).casefold() if isinstance(p, PureWindowsPath) else str(p)


def mapped(value, mappings, required=False):
    p = pure(value)
    for old, new in sorted(mappings.items(), key=lambda item: len(pure(item[0]).parts), reverse=True):
        base = pure(old)
        if type(base) is not type(p):
            continue
        try:
            return str(pure(new) / p.relative_to(base))
        except ValueError:
            pass
    if required:
        raise RescueError("No explicit path mapping for: " + str(value))
    return str(value)


def rebase_policy(value, mappings):
    if isinstance(value, dict):
        return {k: rebase_policy(v, mappings) for k, v in value.items()}
    if isinstance(value, list):
        return [rebase_policy(v, mappings) for v in value]
    if isinstance(value, str):
        return mapped(value, mappings)
    return value


def native_projects(db):
    if not {"projects", "project_roots", "threads"} <= tables(db):
        raise RescueError("This version requires native projects/project_roots/threads tables")
    return [dict(row, roots=[r[0] for r in db.execute(
        "SELECT path FROM project_roots WHERE project_id=? ORDER BY position", (row["id"],))])
            for row in db.execute("SELECT * FROM projects ORDER BY id")]


def inspect_home(source):
    with tempfile.TemporaryDirectory(prefix="codex-pe-inspect-") as temp:
        capture_source(source, temp, ("state_5.sqlite",))
        with contextlib.closing(connect(Path(temp) / "state_5.sqlite", True)) as db:
            projects = native_projects(db)
            threads = [dict(row) for row in db.execute(
                "SELECT id,title,cwd,project_id FROM threads ORDER BY id")]
    return {"version": VERSION, "projects": projects, "threads": threads,
            "notice": "Titles and paths are private. Inspection does not prove images or sessions are complete."}


def select_threads(db, config):
    projects = native_projects(db)
    known = {p["id"]: p for p in projects}
    wanted = set(config.get("project_ids", []))
    if wanted - known.keys():
        raise RescueError("Unknown project IDs: " + ", ".join(sorted(wanted - known.keys())))
    rows = {row["id"]: dict(row) for row in db.execute("SELECT * FROM threads")}
    selected = set(config.get("thread_ids", []))
    if selected - rows.keys():
        raise RescueError("Unknown thread ID")
    roots = [(pure(root), project["id"]) for project in projects for root in project["roots"]]
    owners = {}
    for tid, row in rows.items():
        owner = row.get("project_id")
        if not owner:
            matches = []
            for root, pid in roots:
                try:
                    pure(row["cwd"]).relative_to(root)
                    matches.append((len(root.parts), pid))
                except (ValueError, TypeError):
                    pass
            owner = max(matches)[1] if matches else None
        owners[tid] = owner
        if owner in wanted:
            selected.add(tid)
    if not selected:
        raise RescueError("Selection is empty")
    edges = list(db.execute("SELECT * FROM thread_spawn_edges")) if "thread_spawn_edges" in tables(db) else []
    while True:
        previous = set(selected)
        for edge in edges:
            if edge["parent_thread_id"] in selected:
                selected.add(edge["child_thread_id"])
                if not owners.get(edge["child_thread_id"]):
                    owners[edge["child_thread_id"]] = owners.get(edge["parent_thread_id"])
        if selected == previous:
            break
    if selected - rows.keys():
        raise RescueError("A selected child thread is missing")
    child_ids = {r["child_thread_id"] for r in edges if r["parent_thread_id"] in selected}
    main = selected - child_ids
    wanted |= {owners[tid] for tid in selected if owners.get(tid)}
    return sorted(selected), sorted(main), [p for p in projects if p["id"] in wanted], {
        tid: owners.get(tid) for tid in selected}


@contextlib.contextmanager
def session_stream(path):
    with Path(path).open("rb") as raw:
        if str(path).endswith(".zst"):
            try:
                import zstandard
            except ImportError as exc:
                raise RescueError("Compressed history requires: python -m pip install '.[zstd]'") from exc
            # stream_reader can finish at an incomplete frame without an EOF error.
            # Validate frame completion first, with small chunks to bound expansion.
            try:
                decoder = zstandard.ZstdDecompressor(max_window_size=128 * 1024).decompressobj()
                complete = False
                pending = False
                while chunk := raw.read(128):
                    while chunk:
                        decoder.decompress(chunk)
                        if decoder.eof:
                            complete = True
                            pending = False
                            chunk = decoder.unused_data
                            decoder = zstandard.ZstdDecompressor(max_window_size=128 * 1024).decompressobj()
                        else:
                            pending = True
                            chunk = b""
                if pending or not complete:
                    raise RescueError("Truncated or empty Zstandard session")
                raw.seek(0)
                with zstandard.ZstdDecompressor(max_window_size=128 * 1024).stream_reader(
                        raw, read_across_frames=True, closefd=False) as reader:
                    with io.BufferedReader(reader) as buffered:
                        yield buffered
            except zstandard.ZstdError as exc:
                raise RescueError("Invalid Zstandard session") from exc
        else:
            yield raw


def events(stream):
    while True:
        line = stream.readline(MAX_EVENT + 1)
        if not line:
            return
        if len(line) > MAX_EVENT:
            raise RescueError("Individual JSON event exceeds the 64 MiB limit")
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError) as exc:
            raise RescueError("Invalid or truncated session JSON") from exc
        if not isinstance(event, dict):
            raise RescueError("Session event is not a JSON object")
        yield line, event


def translate(record, position):
    if not 0 <= position <= record["source_size"]:
        raise RescueError("History offset is outside its uncompressed source")
    changes = record["changes"]
    index = bisect.bisect_right([r[0] for r in changes], position) - 1
    if index < 0:
        return position
    start, end, before, after = changes[index]
    if start < position < end:
        raise RescueError("History offset points inside rewritten metadata")
    return position + (after if position >= end else before)


def prepare_sessions(source, workspace, selected, mappings):
    directory = member(source, "sessions")
    index = {}
    for path in directory.rglob("rollout-*"):
        if not (path.name.endswith(".jsonl") or path.name.endswith(".jsonl.zst")):
            continue
        member(source, path.relative_to(source))
        ids = UUID.findall(path.name)
        if not ids:
            continue
        physical = ids[-1].lower()
        if physical in index:
            raise RescueError("Duplicate physical session ID: " + physical)
        index[physical] = (path, ids[0].lower())
    wanted = {pid for pid, (_, logical) in index.items() if logical in selected}
    rawdir = Path(workspace) / "unpacked"
    rawdir.mkdir()
    records = {}
    while wanted - records.keys():
        for physical in sorted(wanted - records.keys()):
            if physical not in index:
                raise RescueError("Required history-base session is missing: " + physical)
            path, logical = index[physical]
            before = digest(path)
            rawpath = rawdir / (physical + ".jsonl")
            with session_stream(path) as stream, rawpath.open("wb") as output:
                first = None
                size = 0
                for raw, event in events(stream):
                    first = event if first is None else first
                    output.write(raw)
                    size += len(raw)
            if digest(path) != before:
                raise RescueError("Source session changed during copying")
            if not first or first.get("type") != "session_meta":
                raise RescueError("Missing session_meta header")
            meta = first.get("payload", {})
            if str(meta.get("id", "")).lower() != physical:
                raise RescueError("Session identity does not match filename")
            base = meta.get("history_base", {}).get("thread_id")
            relative = path.relative_to(source).as_posix().removesuffix(".zst")
            records[physical] = {"relative": relative, "logical": logical, "base": base,
                                 "source_size": size, "changes": []}
            if base:
                wanted.add(base)
    done = set()
    while len(done) < len(records):
        progressed = False
        for physical, record in records.items():
            if physical in done or (record["base"] and record["base"] not in done):
                continue
            target = member(Path(workspace) / "payload", record["relative"])
            target.parent.mkdir(parents=True, exist_ok=True)
            old_offset = new_offset = 0
            with (rawdir / (physical + ".jsonl")).open("rb") as stream, target.open("wb") as output:
                for raw, event in events(stream):
                    rewritten = raw
                    if event.get("type") in ("session_meta", "turn_context"):
                        payload = event["payload"]
                        if payload.get("cwd"):
                            payload["cwd"] = mapped(payload["cwd"], mappings, required=True)
                        if "runtime_workspace_roots" in payload:
                            payload["runtime_workspace_roots"] = [
                                mapped(root, mappings, required=True) for root in payload["runtime_workspace_roots"]]
                        if "sandbox_policy" in payload:
                            payload["sandbox_policy"] = {"type": "read-only"}
                        base = payload.get("history_base")
                        if base and base.get("end_byte_offset") is not None:
                            base["end_byte_offset"] = translate(records[base["thread_id"]], base["end_byte_offset"])
                        rewritten = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode() + (
                            b"\n" if raw.endswith(b"\n") else b"")
                    if raw != rewritten:
                        record["changes"].append([old_offset, old_offset + len(raw),
                                                   new_offset - old_offset,
                                                   new_offset + len(rewritten) - old_offset - len(raw)])
                    output.write(rewritten)
                    old_offset += len(raw)
                    new_offset += len(rewritten)
            record["sha256"] = digest(target)
            done.add(physical)
            progressed = True
        if not progressed:
            raise RescueError("Cycle in history-base dependency chain")
    return records


def load_optional(path, default):
    return read_json(path) if Path(path).is_file() else default


def build_merge(workspace, target_home, output):
    """Rebuild from the latest target, preserving existing rows. Output is isolated."""
    workspace, target_home, output = map(Path, (workspace, target_home, output))
    plan = read_json(workspace / "plan.json")
    output.mkdir(parents=True, exist_ok=False)
    for relative in DATABASES:
        snapshot(member(target_home, relative), member(output, relative))
    with contextlib.closing(connect(workspace / "source/state_5.sqlite", True)) as source, \
            contextlib.closing(connect(output / "state_5.sqlite")) as target:
        require_schema(source, target)
        old = {r["id"]: dict(r) for r in source.execute("SELECT * FROM threads")}
        existing = {r["id"]: dict(r) for r in target.execute("SELECT * FROM threads")}
        selected = set(plan["selected_ids"])
        if selected & existing.keys():
            raise RescueError("Selected thread IDs already exist; divergent histories are not overwritten")
        source_accounts = {old[t].get("creator_account_id") for t in selected} - {None}
        target_accounts = {r.get("creator_account_id") for r in existing.values()} - {None}
        if source_accounts and target_accounts and source_accounts != target_accounts:
            raise RescueError("Source and target chats have different account identities")
        projects = {}
        for project in plan["projects"]:
            roots = [mapped(root, plan["path_map"], True) for root in project["roots"]]
            candidates = [p for p in native_projects(target)
                          if [path_key(r) for r in p["roots"]] == [path_key(r) for r in roots]]
            if len(candidates) > 1:
                raise RescueError("Ambiguous destination project roots")
            if candidates:
                pid = candidates[0]["id"]
            else:
                if target.execute("SELECT 1 FROM projects WHERE id=?", (project["id"],)).fetchone():
                    raise RescueError("Project ID already exists with different roots")
                row = {k: v for k, v in project.items() if k != "roots"}
                insert(target, "projects", row)
                pid = project["id"]
                for original in source.execute("SELECT * FROM project_roots WHERE project_id=?", (pid,)):
                    row = dict(original)
                    row["path"] = mapped(row["path"], plan["path_map"], True)
                    insert(target, "project_roots", row)
            projects[project["id"]] = {"id": pid, "roots": roots, "name": project["name"]}
        # Only import sections actually referenced by selected threads.
        for fk in source.execute("PRAGMA foreign_key_list(threads)"):
            if fk["table"] == "thread_sections":
                for sid in {old[t].get(fk["from"]) for t in selected} - {None}:
                    row = source.execute("SELECT * FROM thread_sections WHERE id=?", (sid,)).fetchone()
                    previous = target.execute("SELECT * FROM thread_sections WHERE id=?", (sid,)).fetchone()
                    if row is None or (previous is not None and dict(previous) != dict(row)):
                        raise RescueError("Referenced section missing or conflicting")
                    if previous is None:
                        insert(target, "thread_sections", dict(row))
        for tid in sorted(selected):
            row = old[tid].copy()
            ids = UUID.findall(pure(row["rollout_path"]).name)
            if not ids or ids[-1].lower() not in plan["sessions"]:
                raise RescueError("Thread rollout file is missing from the recovery plan")
            record = plan["sessions"][ids[-1].lower()]
            row["rollout_path"] = str(member(target_home, record["relative"]))
            row["cwd"] = mapped(row["cwd"], plan["path_map"], True)
            owner = plan["owners"].get(tid)
            if owner:
                row["project_id"] = projects[owner]["id"]
            if "sandbox_policy" in row:
                row["sandbox_policy"] = '{"type":"read-only"}'
            for field in ("memory_enabled", "daybreak_enabled"):
                if field in row:
                    row[field] = 0
            insert(target, "threads", row)
        for table in RELATED_TABLES:
            if table in tables(source):
                for original in source.execute("SELECT * FROM " + quote(table)):
                    if original["thread_id"] in selected:
                        insert(target, table, dict(original))
        if "thread_spawn_edges" in tables(source):
            for original in source.execute("SELECT * FROM thread_spawn_edges"):
                if original["parent_thread_id"] in selected and original["child_thread_id"] in selected:
                    insert(target, "thread_spawn_edges", dict(original))
        for tid, row in existing.items():
            if dict(target.execute("SELECT * FROM threads WHERE id=?", (tid,)).fetchone()) != row:
                raise RescueError("Existing thread changed during merge")
        target.commit()
        check_db(target)
    counts = {}
    with contextlib.closing(connect(workspace / "source/thread_history_1.sqlite", True)) as source, \
            contextlib.closing(connect(output / "thread_history_1.sqlite")) as target:
        require_schema(source, target)
        history_ids = set(plan["selected_ids"]) | plan["sessions"].keys()
        for table in HISTORY_TABLES:
            if table not in tables(source):
                raise RescueError("Required history table missing: " + table)
            count = 0
            for original in source.execute("SELECT * FROM " + quote(table)):
                if original["thread_id"] not in history_ids:
                    continue
                row = dict(original)
                for field in ("rollout_byte_offset", "rollout_end_byte_offset", "next_rollout_byte_offset"):
                    if row.get(field) is not None:
                        record = plan["sessions"].get(row["thread_id"])
                        if record is None:
                            raise RescueError("Offset history segment is missing")
                        row[field] = translate(record, row[field])
                insert(target, table, row)
                count += 1
            counts[table] = count
        target.commit()
        check_db(target)
    with contextlib.closing(connect(workspace / "source/sqlite/codex-dev.db", True)) as source, \
            contextlib.closing(connect(output / "sqlite/codex-dev.db")) as target:
        require_schema(source, target)
        required = {"local_thread_catalog", "local_thread_catalog_sync_state", "local_thread_catalog_metadata"}
        if not required <= tables(source):
            raise RescueError("Unsupported desktop catalog layout")
        sequence = target.execute(
            "SELECT coalesce(max(observation_sequence),0) FROM local_thread_catalog WHERE host_id='local'").fetchone()[0]
        for original in source.execute("SELECT * FROM local_thread_catalog WHERE host_id='local'"):
            if original["thread_id"] not in plan["main_ids"]:
                continue
            row = dict(original)
            sequence += 1
            row["cwd"] = mapped(row["cwd"], plan["path_map"], True)
            row["observation_sequence"] = sequence
            owner = plan["owners"].get(row["thread_id"])
            if owner in projects:
                row["project_id"] = projects[owner]["id"]
            insert(target, "local_thread_catalog", row)
        target.execute("UPDATE local_thread_catalog_sync_state SET watermark_updated_at=NULL,"
                       "initial_build_complete=0,observation_sequence=? WHERE host_id='local'", (sequence,))
        target.execute("UPDATE local_thread_catalog_metadata SET catalog_revision=catalog_revision+1")
        target.commit()
        check_db(target)
    current = load_optional(target_home / METADATA[0], {})
    registry = current.setdefault("local-projects", {})
    host = "local:" + str(target_home)
    identities = current.setdefault("app-server-project-id-by-legacy-project-id-by-host", {}).setdefault(host, {})
    legacy_ids = {}
    for old_id, p in projects.items():
        candidates = [key for key, value in registry.items()
                      if isinstance(value, dict) and
                      [path_key(r) for r in value.get("rootPaths", [])] == [path_key(r) for r in p["roots"]]]
        if len(candidates) > 1:
            raise RescueError("Ambiguous legacy project roots in current app state")
        legacy = candidates[0] if candidates else str(uuid.uuid4())
        registry.setdefault(legacy, {"name": p["name"], "rootPaths": p["roots"]})
        identities[legacy] = p["id"]
        legacy_ids[old_id] = legacy
        order = current.setdefault("project-order", [])
        if legacy not in order:
            order.append(legacy)
    for tid in plan["main_ids"]:
        owner = plan["owners"].get(tid)
        if owner in projects:
            current.setdefault("thread-project-assignments", {})[tid] = {
                "projectKind": "local", "projectId": legacy_ids[owner]}
            current.setdefault("thread-project-membership-host-ids", {})[tid] = "local"
            current.setdefault("thread-writable-roots", {})[tid] = projects[owner]["roots"]
    write_json(output / METADATA[0], current)
    write_json(output / METADATA[1], current)
    existing_lines = (target_home / METADATA[2]).read_text(encoding="utf-8-sig").splitlines() \
        if (target_home / METADATA[2]).is_file() else []
    ids = {json.loads(line)["id"] for line in existing_lines if line.strip()}
    source_index = workspace / "source" / METADATA[2]
    additions = [line for line in source_index.read_text(encoding="utf-8-sig").splitlines()
                 if line.strip() and json.loads(line).get("id") in plan["main_ids"]
                 and json.loads(line)["id"] not in ids] if source_index.is_file() else []
    (output / METADATA[2]).write_text("\n".join(existing_lines + additions) + "\n", encoding="utf-8")
    for record in plan["sessions"].values():
        existing_file = member(target_home, record["relative"])
        if existing_file.exists() and digest(existing_file) != record["sha256"]:
            raise RescueError("Existing session file has conflicting content")
    return {"projects": len(projects), "main_threads": len(plan["main_ids"]),
            "all_threads": len(plan["selected_ids"]), "segments": len(plan["sessions"]),
            "history_rows": counts, "existing_threads_preserved": len(existing),
            "roots": [root for p in projects.values() for root in p["roots"]],
            "attachment_status": "Image/external attachment binaries are not recovered by v0.1; verify separately."}


def prepare(config_file, workspace):
    config = read_json(config_file)
    required = {"source_home", "target_home", "path_map"}
    if not required <= config.keys() or config.keys() - required - {"project_ids", "thread_ids"}:
        raise RescueError("Config must contain source_home, target_home, path_map and project_ids/thread_ids")
    source, target, workspace = [Path(x).expanduser().resolve()
                                 for x in (config["source_home"], config["target_home"], workspace)]
    if any(contained(a, b) or contained(b, a) for a, b in
           ((source, target), (workspace, source), (workspace, target))):
        raise RescueError("Source, target and recovery workspace must be disjoint directories")
    if not config["path_map"] or not isinstance(config["path_map"], dict):
        raise RescueError("Explicit old-to-new path_map is required")
    for old, new in config["path_map"].items():
        if not pure(old).is_absolute() or not pure(new).is_absolute():
            raise RescueError("Mappings must use absolute paths")
    if workspace.exists():
        raise RescueError("Workspace already exists; choose a new empty location")
    workspace.mkdir(parents=True)
    source_fingerprint = capture_source(source, workspace / "source")
    with contextlib.closing(connect(workspace / "source/state_5.sqlite", True)) as db:
        selected, main, projects, owners = select_threads(db, config)
    sessions = prepare_sessions(source, workspace, set(selected), config["path_map"])
    plan = {"version": VERSION, "source_home": str(source), "target_home": str(target),
            "path_map": config["path_map"], "selected_ids": selected, "main_ids": main,
            "projects": projects, "sessions": sessions, "owners": owners,
            "source_fingerprint": source_fingerprint}
    write_json(workspace / "plan.json", plan)
    report = build_merge(workspace, target, workspace / "preview")
    write_json(workspace / "preview.json", report)
    files = {}
    for directory in ("source", "payload"):
        for path in sorted((workspace / directory).rglob("*")):
            if path.is_file():
                files[path.relative_to(workspace).as_posix()] = digest(path)
    files["plan.json"] = digest(workspace / "plan.json")
    write_json(workspace / "verified.json", {
        "version": VERSION, "engine_sha256": digest(__file__), "files": files})
    return report


def verify(workspace):
    workspace = Path(workspace).resolve()
    receipt = read_json(workspace / "verified.json")
    if receipt["version"] != VERSION or receipt["engine_sha256"] != digest(__file__):
        raise RescueError("Tool changed after preparation; create a new recovery workspace")
    for name, expected in receipt["files"].items():
        if digest(member(workspace, name)) != expected:
            raise RescueError("Prepared recovery file changed: " + name)
    return read_json(workspace / "plan.json")


def require_windows_closed():
    if sys.platform != "win32":
        raise RescueError("v0.1 modifying apply/rollback is supported on Windows only")
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class Entry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                    ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD),
                    ("name", wintypes.WCHAR * 260)]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise RescueError("Cannot inspect Windows processes")
    found = []
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(Entry)
        more = kernel.Process32FirstW(handle, ctypes.byref(entry))
        if not more:
            raise RescueError("Process enumeration failed")
        while more:
            if entry.name.lower() in {"chatgpt.exe", "codex.exe", "codex-code-mode-host.exe"}:
                found.append({"name": entry.name, "pid": entry.pid})
            more = kernel.Process32NextW(handle, ctypes.byref(entry))
        if ctypes.get_last_error() not in (0, 18):
            raise RescueError("Process enumeration did not finish normally")
    finally:
        kernel.CloseHandle(handle)
    if found:
        raise RescueError("Close Codex/ChatGPT desktop, CLI and IDE backends first: " + json.dumps(found))


@contextlib.contextmanager
def target_lock(home):
    path = member(home, ".pe-rescue.lock")
    with path.open("a+b") as stream:
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:  # Internal synthetic tests; CLI modifying commands still reject non-Windows.
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def replace_copy(source, target):
    """Copy across volumes, then atomically replace only within the target directory."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".pe-rescue-new")
    if temp.exists():
        raise RescueError("Stale staging file requires inspection: " + str(temp))
    try:
        shutil.copy2(source, temp)
        if digest(temp) != digest(source):
            raise RescueError("Copied file failed SHA-256 verification")
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()


def archive_remove(source, destination):
    """Copy + verify + unlink; no cross-volume os.replace."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RescueError("Archive destination already exists")
    shutil.copy2(source, destination)
    if digest(source) != digest(destination):
        raise RescueError("Archive failed SHA-256 verification")
    source.unlink()


def restore_snapshot(home, backup, receipt):
    for relative, expected in receipt["before_hashes"].items():
        if digest(member(backup / "before", relative)) != expected:
            raise RescueError("Original recovery snapshot changed; automatic restore stopped")
    # SQLite backup snapshots already include WAL contents. Never reattach old WAL.
    for relative in DATABASES:
        for suffix in ("-wal", "-shm"):
            path = member(home, relative + suffix)
            if path.exists():
                archive_remove(path, member(backup / ("rollback-journals-" + uuid.uuid4().hex), relative + suffix))
    for relative, existed in receipt["existed"].items():
        path = member(home, relative)
        if existed:
            replace_copy(member(backup / "before", relative), path)
        elif path.exists():
            archive_remove(path, member(backup / "removed", relative))
    for relative in receipt["added"]:
        path = member(home, relative)
        if path.exists():
            archive_name = hashlib.sha256(relative.encode()).hexdigest()[:24] + path.suffix
            archive_remove(path, member(backup / "removed-assets", archive_name))
    for relative in DATABASES:
        with contextlib.closing(connect(member(home, relative), True)) as db:
            check_db(db)


def apply(workspace, guard=None):
    guard = require_windows_closed if guard is None else guard
    workspace = Path(workspace).resolve()
    plan = verify(workspace)
    home = Path(plan["target_home"])
    guard()
    for project in plan["projects"]:
        for root in project["roots"]:
            if not Path(mapped(root, plan["path_map"], True)).is_dir():
                raise RescueError("Restore actual project files first; target root missing: " + root)
    with target_lock(home):
        guard()
        before = fingerprint(home)
        stage = workspace / ("apply-stage-" + uuid.uuid4().hex)
        report = build_merge(workspace, home, stage)
        if fingerprint(home) != before:
            raise RescueError("Destination changed during merge; no application records were installed")
        guard()
        backup = member(home, "pe-rescue-backups/" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex)
        backup.mkdir(parents=True)
        existed = {}
        for relative in MANAGED:
            source = member(home, relative)
            existed[relative] = source.is_file()
            if source.is_file():
                target = member(backup / "before", relative)
                if relative in DATABASES:
                    snapshot(source, target)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
        receipt = {"version": VERSION, "state": "prepared", "target_home": str(home),
                   "backup": str(backup), "existed": existed, "added": [],
                   "before_hashes": {r: digest(member(backup / "before", r))
                                     for r, exists in existed.items() if exists},
                   "protected": {x: before[x] for x in PROTECTED}, "report": report}
        write_json(backup / "receipt.json", receipt)
        if fingerprint(home) != before:
            raise RescueError("Destination changed before installation")
        guard()
        try:
            receipt["state"] = "installing"
            write_json(backup / "receipt.json", receipt)
            for record in plan["sessions"].values():
                destination = member(home, record["relative"])
                if not destination.exists():
                    receipt["added"].append(record["relative"])
                    write_json(backup / "receipt.json", receipt)
                    replace_copy(member(workspace / "payload", record["relative"]), destination)
                elif digest(destination) != record["sha256"]:
                    raise RescueError("Session collision during installation")
            guard()
            if fingerprint(home) != before:
                raise RescueError("Destination changed immediately before database installation")
            for relative in DATABASES:
                for suffix in ("-wal", "-shm"):
                    path = member(home, relative + suffix)
                    if path.exists():
                        archive_remove(path, member(backup / "diagnostic-sidecars", relative + suffix))
            for relative in MANAGED:
                guard()
                replace_copy(member(stage, relative), member(home, relative))
            for relative in DATABASES:
                with contextlib.closing(connect(member(home, relative), True)) as db:
                    check_db(db)
            after = fingerprint(home)
            if any(after[name] != before[name] for name in PROTECTED):
                raise RescueError("Protected authentication/configuration file changed")
            receipt.update(state="complete", after=after,
                           added_hashes={r: digest(member(home, r)) for r in receipt["added"]})
            write_json(backup / "receipt.json", receipt)
        except Exception as exc:
            receipt["error"] = str(exc)
            try:
                guard()
                restore_snapshot(home, backup, receipt)
                receipt["state"] = "rolled_back"
            except Exception as rollback_error:
                receipt.update(state="rollback_incomplete", rollback_error=str(rollback_error))
            write_json(backup / "receipt.json", receipt)
            raise RescueError("Installation failed; state=" + receipt["state"] +
                              "; preserve this receipt: " + str(backup / "receipt.json")) from exc
        return {"state": "complete", "receipt": str(backup / "receipt.json"), **report}


def rollback(receipt_path, guard=None):
    guard = require_windows_closed if guard is None else guard
    receipt_path = Path(receipt_path).resolve()
    receipt = read_json(receipt_path)
    home = Path(receipt["target_home"]).resolve()
    backup = Path(receipt["backup"]).resolve()
    if receipt_path != member(backup, "receipt.json") or not contained(backup, home / "pe-rescue-backups"):
        raise RescueError("Receipt is outside the target backup directory")
    if receipt["state"] != "complete":
        raise RescueError("Only a completed, unchanged installation supports automatic rollback")
    guard()
    with target_lock(home):
        if fingerprint(home) != receipt["after"]:
            raise RescueError("Destination changed after recovery; automatic rollback would discard newer data")
        for relative, expected in receipt["added_hashes"].items():
            if not member(home, relative).exists() or digest(member(home, relative)) != expected:
                raise RescueError("Recovered session changed; rollback requires manual review")
        guard()
        restore_snapshot(home, backup, receipt)
        receipt["state"] = "rolled_back"
        write_json(receipt_path, receipt)
    return {"state": "rolled_back", "receipt": str(receipt_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("inspect", help="Read an offline backup via a temporary copy")
    scan.add_argument("--source-home", required=True, type=Path)
    prep = commands.add_parser("prepare", help="Build an isolated preview; do not install it")
    prep.add_argument("--config", required=True, type=Path)
    prep.add_argument("--workspace", required=True, type=Path)
    check = commands.add_parser("verify", help="Verify prepared data hashes")
    check.add_argument("--workspace", required=True, type=Path)
    for name in ("apply", "rollback"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--workspace" if name == "apply" else "--receipt", required=True, type=Path)
        cmd.add_argument("--yes", action="store_true")
        cmd.add_argument("--codex-stopped", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in ("apply", "rollback") and not (args.yes and args.codex_stopped):
            raise RescueError("Modifying commands require --yes --codex-stopped; detection cannot be bypassed")
        if args.command == "inspect":
            result = inspect_home(args.source_home.resolve())
        elif args.command == "prepare":
            result = prepare(args.config, args.workspace)
        elif args.command == "verify":
            plan = verify(args.workspace)
            result = {"verified": True, "threads": len(plan["selected_ids"]),
                      "segments": len(plan["sessions"])}
        elif args.command == "apply":
            result = apply(args.workspace)
        else:
            result = rollback(args.receipt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RescueError, OSError, sqlite3.Error, ValueError, KeyError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
