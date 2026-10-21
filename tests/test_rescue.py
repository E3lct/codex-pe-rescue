"""All records, messages, account labels and paths here are synthetic."""
import contextlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

import rescue

MAIN = "11111111-1111-4111-8111-111111111111"
BRANCH = "22222222-2222-4222-8222-222222222222"
EXISTING = "99999999-9999-4999-8999-999999999999"
UNRELATED = "44444444-4444-4444-8444-444444444444"
OLD_ROOT = r"D:\OldProjects\Demo"

STATE_SQL = """
CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,position INTEGER);
CREATE TABLE project_roots(project_id TEXT REFERENCES projects(id),position INTEGER,path TEXT,
 PRIMARY KEY(project_id,position));
CREATE TABLE thread_sections(id TEXT PRIMARY KEY,name TEXT);
CREATE TABLE threads(id TEXT PRIMARY KEY,rollout_path TEXT,cwd TEXT,source TEXT,
 project_id TEXT REFERENCES projects(id),title TEXT,creator_account_id TEXT,
 sandbox_policy TEXT,section_id TEXT REFERENCES thread_sections(id),archived INTEGER DEFAULT 0);
CREATE TABLE thread_spawn_edges(parent_thread_id TEXT REFERENCES threads(id),
 child_thread_id TEXT REFERENCES threads(id),PRIMARY KEY(parent_thread_id,child_thread_id));
CREATE TABLE thread_dynamic_tools(thread_id TEXT REFERENCES threads(id),name TEXT,
 PRIMARY KEY(thread_id,name));
CREATE TABLE thread_attachments(thread_id TEXT REFERENCES threads(id),name TEXT,
 PRIMARY KEY(thread_id,name));
CREATE TABLE thread_read_receipts(thread_id TEXT PRIMARY KEY REFERENCES threads(id),seen INTEGER);
CREATE TABLE _sqlx_migrations(version INTEGER PRIMARY KEY,checksum BLOB,success INTEGER);
INSERT INTO _sqlx_migrations VALUES(1,X'0102',1);
"""
HISTORY_SQL = """
CREATE TABLE thread_turns(id TEXT PRIMARY KEY,thread_id TEXT,rollout_byte_offset INTEGER,payload TEXT);
CREATE TABLE thread_items(id TEXT PRIMARY KEY,thread_id TEXT,rollout_byte_offset INTEGER,
 rollout_end_byte_offset INTEGER,payload TEXT);
CREATE TABLE thread_history_projection_state(thread_id TEXT PRIMARY KEY,next_rollout_byte_offset INTEGER);
CREATE TABLE thread_realtime_items(id TEXT PRIMARY KEY,thread_id TEXT,payload TEXT);
"""
CATALOG_SQL = """
CREATE TABLE local_thread_catalog(thread_id TEXT PRIMARY KEY,host_id TEXT,cwd TEXT,
 project_id TEXT,observation_sequence INTEGER);
CREATE TABLE local_thread_catalog_sync_state(host_id TEXT PRIMARY KEY,watermark_updated_at TEXT,
 initial_build_complete INTEGER,observation_sequence INTEGER);
CREATE TABLE local_thread_catalog_metadata(catalog_revision INTEGER);
INSERT INTO local_thread_catalog_sync_state VALUES('local',NULL,1,1);
INSERT INTO local_thread_catalog_metadata VALUES(1);
"""


@contextlib.contextmanager
def database(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def create_home(home):
    home.mkdir()
    for relative, sql in zip(rescue.DATABASES, (STATE_SQL, HISTORY_SQL, CATALOG_SQL)):
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with database(path) as db:
            db.executescript(sql)
    rescue.write_json(home / ".codex-global-state.json", {"keep": "current-ui-state"})
    (home / "session_index.jsonl").write_text("", encoding="utf-8")
    (home / "auth.json").write_text('{"dummy":"synthetic-only"}', encoding="utf-8")
    (home / "config.toml").write_text("# synthetic configuration\n", encoding="utf-8")


def add_thread(home, tid, root, project, rollout, title="Synthetic lesson"):
    with database(home / "state_5.sqlite") as db:
        db.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?)", (project, project, 0))
        db.execute("INSERT OR IGNORE INTO project_roots VALUES(?,?,?)", (project, 0, str(root)))
        db.execute("INSERT OR IGNORE INTO thread_sections VALUES(?,?)", (project, "Synthetic section"))
        db.execute("INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (tid, str(rollout), str(root), "vscode", project, title, "synthetic-account",
                    '{"type":"workspace-write"}', project, 0))
    with database(home / "sqlite/codex-dev.db") as db:
        db.execute("INSERT INTO local_thread_catalog VALUES(?,?,?,?,?)",
                   (tid, "local", str(root), project, 1))


def dump_db(path):
    with database(path) as db:
        return "\n".join(db.iterdump())


def bytes_tree(home):
    return {p.relative_to(home).as_posix(): rescue.digest(p)
            for p in home.rglob("*") if p.is_file()}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.target = self.root / "pe-copy", self.root / "new-profile"
        self.project = self.root / "new-project"
        self.project.mkdir()
        create_home(self.source)
        create_home(self.target)
        self.session_dir = self.source / "sessions/2026/01/01"
        self.session_dir.mkdir(parents=True)
        self.base = self.session_dir / ("rollout-2026-01-01T00-00-00-" + MAIN + ".jsonl")
        self.child = self.session_dir / ("rollout-2026-01-01T01-00-00-" + MAIN + "_" + BRANCH + ".jsonl")
        header = json.dumps({"type": "session_meta", "payload": {
            "id": MAIN, "cwd": OLD_ROOT, "history_mode": "paginated",
            "runtime_workspace_roots": [OLD_ROOT]}}).encode() + b"\n"
        self.message = json.dumps({"type": "response_item", "payload": {
            "type": "message", "text": "Synthetic message with old path " + OLD_ROOT}}).encode() + b"\n"
        self.base.write_bytes(header + self.message)
        self.old_start = len(header)
        self.child.write_bytes(json.dumps({"type": "session_meta", "payload": {
            "id": BRANCH, "cwd": OLD_ROOT, "history_mode": "paginated",
            "history_base": {"thread_id": MAIN, "end_byte_offset": len(header + self.message)}}}).encode()
            + b"\n" + self.message)
        add_thread(self.source, MAIN, OLD_ROOT, "source-project",
                   r"C:\Users\Example\.codex\sessions\2026\01\01" + "\\" + self.child.name)
        add_thread(self.source, UNRELATED, r"D:\Unrelated", "unrelated-project", "not-selected.jsonl")
        add_thread(self.target, EXISTING, self.project, "existing-project", "existing.jsonl", "Keep me")
        with database(self.source / "thread_history_1.sqlite") as db:
            db.execute("INSERT INTO thread_items VALUES(?,?,?,?,?)",
                       ("synthetic-item", MAIN, self.old_start,
                        len(header + self.message), '{"text":"synthetic"}'))
            db.execute("INSERT INTO thread_history_projection_state VALUES(?,?)",
                       (MAIN, len(header + self.message)))
        (self.source / "session_index.jsonl").write_text(
            json.dumps({"id": MAIN, "title": "Synthetic lesson"}) + "\n", encoding="utf-8")
        (self.target / "session_index.jsonl").write_text(
            json.dumps({"id": EXISTING, "title": "Keep me"}) + "\n", encoding="utf-8")
        self.config = self.root / "config.json"
        rescue.write_json(self.config, {"source_home": str(self.source), "target_home": str(self.target),
                          "project_ids": ["source-project"], "thread_ids": [],
                          "path_map": {OLD_ROOT: str(self.project)}})
        self.workspace = self.root / "recovery-work"

    def prepare(self):
        return rescue.prepare(self.config, self.workspace)

    def test_prepare_preserves_source_and_target_and_rebases_history(self):
        before_source, before_target = bytes_tree(self.source), bytes_tree(self.target)
        report = self.prepare()
        self.assertEqual(before_source, bytes_tree(self.source))
        self.assertEqual(before_target, bytes_tree(self.target))
        self.assertEqual(report["main_threads"], 1)
        self.assertEqual(report["segments"], 2)
        self.assertEqual(report["existing_threads_preserved"], 1)
        plan = rescue.verify(self.workspace)
        payload = self.workspace / "payload" / plan["sessions"][MAIN]["relative"]
        body = payload.read_bytes()
        self.assertTrue(body.endswith(self.message))
        meta = json.loads(body.splitlines()[0])["payload"]
        self.assertEqual(meta["cwd"], str(self.project))
        self.assertEqual(meta["history_mode"], "paginated")
        with database(self.workspace / "preview/thread_history_1.sqlite") as db:
            offset = db.execute("SELECT rollout_byte_offset FROM thread_items").fetchone()[0]
        self.assertEqual(body[offset:], self.message)
        child = self.workspace / "payload" / plan["sessions"][BRANCH]["relative"]
        self.assertEqual(json.loads(child.read_bytes().splitlines()[0])["payload"]["history_base"]["end_byte_offset"],
                         len(body))

    def test_apply_and_rollback_preserve_existing_rows_credentials_and_source(self):
        source = bytes_tree(self.source)
        original = {r: dump_db(self.target / r) for r in rescue.DATABASES}
        auth = (self.target / "auth.json").read_bytes()
        self.prepare()
        result = rescue.apply(self.workspace, guard=lambda: None)
        self.assertEqual(result["state"], "complete")
        with database(self.target / "state_5.sqlite") as db:
            self.assertEqual(db.execute("SELECT count(*) FROM threads").fetchone()[0], 2)
            row = db.execute("SELECT cwd,sandbox_policy FROM threads WHERE id=?", (MAIN,)).fetchone()
            self.assertEqual(row, (str(self.project), '{"type":"read-only"}'))
            self.assertIsNone(db.execute("SELECT id FROM threads WHERE id=?", (UNRELATED,)).fetchone())
        self.assertEqual(auth, (self.target / "auth.json").read_bytes())
        self.assertEqual(source, bytes_tree(self.source))
        rescue.rollback(result["receipt"], guard=lambda: None)
        self.assertEqual(original, {r: dump_db(self.target / r) for r in rescue.DATABASES})
        self.assertFalse(any((self.target / "sessions").rglob("*.jsonl")))

    def test_install_failure_after_first_database_is_rolled_back(self):
        original = {r: dump_db(self.target / r) for r in rescue.DATABASES}
        self.prepare()
        real = rescue.replace_copy
        failed = False

        def fail_once(source, target):
            nonlocal failed
            if Path(target).resolve() == (self.target / "thread_history_1.sqlite").resolve() and not failed:
                failed = True
                raise OSError("Synthetic injected failure")
            return real(source, target)

        with mock.patch.object(rescue, "replace_copy", side_effect=fail_once):
            with self.assertRaisesRegex(rescue.RescueError, "state=rolled_back"):
                rescue.apply(self.workspace, guard=lambda: None)
        self.assertEqual(original, {r: dump_db(self.target / r) for r in rescue.DATABASES})

    def test_reopen_before_install_prevents_database_changes(self):
        original = {r: dump_db(self.target / r) for r in rescue.DATABASES}
        self.prepare()
        calls = 0

        def guard():
            nonlocal calls
            calls += 1
            if calls >= 4:
                raise rescue.RescueError("Synthetic reopened client")

        with self.assertRaisesRegex(rescue.RescueError, "reopened"):
            rescue.apply(self.workspace, guard=guard)
        self.assertEqual(original, {r: dump_db(self.target / r) for r in rescue.DATABASES})

    def test_same_thread_id_is_rejected(self):
        with database(self.target / "state_5.sqlite") as db:
            db.execute("UPDATE threads SET id=? WHERE id=?", (MAIN, EXISTING))
        with self.assertRaisesRegex(rescue.RescueError, "already exist"):
            self.prepare()

    def test_schema_mismatch_is_rejected(self):
        with database(self.target / "state_5.sqlite") as db:
            db.execute("ALTER TABLE threads ADD COLUMN unknown TEXT")
        with self.assertRaisesRegex(rescue.RescueError, "schemas"):
            self.prepare()

    def test_migration_checksum_mismatch_is_rejected(self):
        with database(self.target / "state_5.sqlite") as db:
            db.execute("UPDATE _sqlx_migrations SET checksum=X'0304'")
        with self.assertRaisesRegex(rescue.RescueError, "schemas"):
            self.prepare()

    def test_different_account_is_rejected(self):
        with database(self.target / "state_5.sqlite") as db:
            db.execute("UPDATE threads SET creator_account_id='other-synthetic-account'")
        with self.assertRaisesRegex(rescue.RescueError, "account"):
            self.prepare()

    def test_missing_base_and_invalid_json_are_rejected(self):
        self.base.unlink()
        with self.assertRaisesRegex(rescue.RescueError, "history-base"):
            self.prepare()

    def test_manifest_tampering_is_rejected(self):
        self.prepare()
        (self.workspace / "plan.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(rescue.RescueError, "changed"):
            rescue.verify(self.workspace)

    def test_path_traversal_and_drive_paths_are_rejected(self):
        for path in ("../outside", r"..\outside", "C:/outside"):
            with self.assertRaises(rescue.RescueError):
                rescue.member(self.root, path)

    def test_longest_mapping_and_windows_case_are_preserved(self):
        mapping = {r"D:\Work": r"E:\Restored", r"D:\Work\Nested": r"F:\Exact"}
        self.assertEqual(rescue.mapped(r"d:\work\nested\src", mapping), r"F:\Exact\src")

    def test_newer_target_changes_block_rollback(self):
        self.prepare()
        result = rescue.apply(self.workspace, guard=lambda: None)
        with database(self.target / "state_5.sqlite") as db:
            db.execute("UPDATE threads SET title='New work' WHERE id=?", (MAIN,))
        with self.assertRaisesRegex(rescue.RescueError, "changed after"):
            rescue.rollback(result["receipt"], guard=lambda: None)

    def test_archive_never_uses_cross_volume_replace(self):
        source, archive = self.root / "original.bin", self.root / "archive/file.bin"
        source.write_bytes(b"synthetic")
        with mock.patch.object(rescue.os, "replace", side_effect=OSError("EXDEV")):
            rescue.archive_remove(source, archive)
        self.assertEqual(archive.read_bytes(), b"synthetic")
        self.assertFalse(source.exists())

    def test_windows_long_paths_are_rejected_before_writes(self):
        with mock.patch.object(rescue.sys, "platform", "win32"):
            with self.assertRaisesRegex(rescue.RescueError, "too long"):
                rescue.member(self.root, "x" * 240)

    def test_readonly_source_wal_is_captured_without_touching_original(self):
        db = sqlite3.connect(self.source / "state_5.sqlite")
        self.addCleanup(db.close)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("INSERT INTO projects VALUES('wal-only','Synthetic WAL project',8)")
        db.commit()
        before = bytes_tree(self.source)
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            rescue.capture_source(self.source, temp)
            with database(Path(temp) / "state_5.sqlite") as snapshot:
                self.assertIsNotNone(snapshot.execute("SELECT id FROM projects WHERE id='wal-only'").fetchone())
        self.assertEqual(before, bytes_tree(self.source))

    def test_project_owner_can_be_inferred_from_root(self):
        with database(self.source / "state_5.sqlite") as db:
            db.execute("UPDATE threads SET project_id=NULL WHERE id=?", (MAIN,))
        self.prepare()
        with database(self.workspace / "preview/state_5.sqlite") as db:
            self.assertEqual(db.execute("SELECT project_id FROM threads WHERE id=?", (MAIN,)).fetchone()[0],
                             "existing-project")

    def test_corrupt_session_is_rejected(self):
        self.base.write_bytes(self.base.read_bytes() + b'{"truncated":')
        with self.assertRaisesRegex(rescue.RescueError, "truncated"):
            self.prepare()

    def test_changed_original_snapshot_blocks_rollback_before_writes(self):
        self.prepare()
        result = rescue.apply(self.workspace, guard=lambda: None)
        receipt = rescue.read_json(result["receipt"])
        snapshot = Path(receipt["backup"]) / "before/state_5.sqlite"
        snapshot.write_bytes(b"synthetic corruption")
        before = rescue.fingerprint(self.target)
        with self.assertRaisesRegex(rescue.RescueError, "snapshot changed"):
            rescue.rollback(result["receipt"], guard=lambda: None)
        self.assertEqual(before, rescue.fingerprint(self.target))

    def test_target_wal_updates_survive_merge_and_snapshot_rollback(self):
        self.prepare()
        # Build offline WAL files without keeping the target open during apply.
        writer_home = self.root / "wal-writer"
        writer_home.mkdir()
        writer_path = writer_home / "state_5.sqlite"
        shutil.copy2(self.target / "state_5.sqlite", writer_path)
        connection = sqlite3.connect(writer_path)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("UPDATE threads SET title='Committed in WAL' WHERE id=?", (EXISTING,))
            connection.commit()
            for suffix in ("", "-wal", "-shm"):
                shutil.copy2(Path(str(writer_path) + suffix),
                             self.target / ("state_5.sqlite" + suffix))
        finally:
            connection.close()
        result = rescue.apply(self.workspace, guard=lambda: None)
        with database(self.target / "state_5.sqlite") as db:
            self.assertEqual(db.execute("SELECT title FROM threads WHERE id=?", (EXISTING,)).fetchone()[0],
                             "Committed in WAL")
        rescue.rollback(result["receipt"], guard=lambda: None)
        with database(self.target / "state_5.sqlite") as db:
            self.assertEqual(db.execute("SELECT title FROM threads WHERE id=?", (EXISTING,)).fetchone()[0],
                             "Committed in WAL")
            self.assertIsNone(db.execute("SELECT id FROM threads WHERE id=?", (MAIN,)).fetchone())
        self.assertFalse((self.target / "state_5.sqlite-wal").exists())

    def test_reopened_client_during_partial_install_blocks_automatic_restore(self):
        self.prepare()
        real = rescue.replace_copy
        client_open = False

        def replace_then_reopen(source, target):
            nonlocal client_open
            real(source, target)
            if Path(target).resolve() == (self.target / "state_5.sqlite").resolve():
                client_open = True

        def guard():
            if client_open:
                raise rescue.RescueError("Synthetic client reopened during install")

        with mock.patch.object(rescue, "replace_copy", side_effect=replace_then_reopen):
            with self.assertRaisesRegex(rescue.RescueError, "state=rollback_incomplete"):
                rescue.apply(self.workspace, guard=guard)
        receipt_path = next((self.target / "pe-rescue-backups").glob("*/receipt.json"))
        receipt = rescue.read_json(receipt_path)
        self.assertEqual(receipt["state"], "rollback_incomplete")
        self.assertTrue((Path(receipt["backup"]) / "before/state_5.sqlite").is_file())


try:
    import zstandard
except ImportError:
    zstandard = None


@unittest.skipIf(zstandard is None, "install the zstd extra")
class CompressedTests(RecoveryTests):
    # Inherit the same invariants with compressed source sessions.
    def setUp(self):
        super().setUp()
        for path in (self.base, self.child):
            compressed = Path(str(path) + ".zst")
            compressed.write_bytes(zstandard.ZstdCompressor(write_checksum=True).compress(path.read_bytes()))
            path.unlink()
        self.base = Path(str(self.base) + ".zst")
        self.child = Path(str(self.child) + ".zst")

    def test_missing_base_and_invalid_json_are_rejected(self):
        self.base.unlink()
        with self.assertRaisesRegex(rescue.RescueError, "history-base"):
            self.prepare()

    def test_corrupt_session_is_rejected(self):
        data = self.base.read_bytes()
        self.base.write_bytes(data[:-3])
        with self.assertRaisesRegex(rescue.RescueError, "Truncated|Invalid"):
            self.prepare()

    def test_concatenated_zstd_frames_are_supported(self):
        raw = zstandard.ZstdDecompressor().decompress(self.base.read_bytes())
        middle = raw.index(b"\n") + 1
        self.base.write_bytes(zstandard.ZstdCompressor().compress(raw[:middle]) +
                              zstandard.ZstdCompressor().compress(raw[middle:]))
        self.prepare()


if __name__ == "__main__":
    unittest.main()
