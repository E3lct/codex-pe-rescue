"""Exercise link/Skill entrypoint behavior using only temporary synthetic profiles."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest import mock

import rescue
import test_rescue as fixtures

HELPER = Path(__file__).resolve().parents[1] / "skills/codex-pe-rescue/scripts/assist.py"
spec = importlib.util.spec_from_file_location("rescue_assist", HELPER)
assist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assist)


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RecoveryTests(methodName="test_prepare_preserves_source_and_target_and_rebases_history")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.case = self.fixture
        self.cache = self.case.root / "cache"

    def prepare(self):
        return assist.prepare_recovery(self.case.source, self.case.target, ["source-project"], [],
                                      [(fixtures.OLD_ROOT, str(self.case.project))], self.case.workspace,
                                      Path(sys.executable), Path(rescue.__file__), self.cache)

    def test_prepare_generates_launcher_and_latest_status_without_profile_writes(self):
        source, target = fixtures.bytes_tree(self.case.source), fixtures.bytes_tree(self.case.target)
        result = self.prepare()
        self.assertEqual(source, fixtures.bytes_tree(self.case.source))
        self.assertEqual(target, fixtures.bytes_tree(self.case.target))
        launcher = Path(result["launcher"]).read_text(encoding="utf-8")
        self.assertIn("pause", launcher)
        self.assertIn("chcp 65001", launcher)
        self.assertIn("DisableDelayedExpansion", launcher)
        self.assertTrue((self.case.workspace / "run-recovery.py").is_file())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(assist.main(["--cache", str(self.cache), "status"]), 0)
        self.assertIsNone(json.loads(output.getvalue())["outcome"])

    def test_wait_then_apply_saves_real_engine_receipt(self):
        self.prepare()
        handoff = assist.read(self.case.workspace / "handoff.json")
        engine = assist.load_engine(handoff["engine"])
        with mock.patch.object(assist, "load_engine", return_value=engine), \
                mock.patch.object(engine, "require_windows_closed", return_value=None), \
                mock.patch.object(assist, "wait_for_closed", side_effect=lambda guard, **kw: guard()):
            result = assist.wait_and_apply(self.case.workspace)
        self.assertEqual(result["state"], "complete")
        saved = assist.read(self.case.workspace / "result.json")
        self.assertEqual(saved["receipt"], result["receipt"])
        with mock.patch.object(assist, "load_engine") as load:
            self.assertEqual(assist.wait_and_apply(self.case.workspace), saved)
            load.assert_not_called()
        with fixtures.database(self.case.target / "state_5.sqlite") as db:
            self.assertIsNotNone(db.execute("SELECT id FROM threads WHERE id=?", (fixtures.MAIN,)).fetchone())

    def test_wait_timeout_preserves_profiles_and_records_outcome(self):
        self.prepare()
        before = rescue.fingerprint(self.case.target)
        def busy():
            raise RuntimeError("Close Codex/ChatGPT synthetic client")
        engine = types.SimpleNamespace(verify=lambda workspace: None, require_windows_closed=busy,
                                       apply=mock.Mock())
        with mock.patch.object(assist, "load_engine", return_value=engine):
            with self.assertRaises(TimeoutError):
                assist.wait_and_apply(self.case.workspace, timeout=0)
        engine.apply.assert_not_called()
        self.assertEqual(before, rescue.fingerprint(self.case.target))
        self.assertEqual(assist.read(self.case.workspace / "result.json")["state"], "waiting_timeout")
        self.assertTrue((self.case.workspace / "failure.log").is_file())

    def test_changed_handoff_engine_is_reported_without_installing(self):
        self.prepare()
        handoff = assist.read(self.case.workspace / "handoff.json")
        Path(handoff["engine"]).write_bytes(b"synthetic corruption")
        before = rescue.fingerprint(self.case.target)
        with self.assertRaisesRegex(RuntimeError, "engine changed"):
            assist.wait_and_apply(self.case.workspace)
        self.assertEqual(before, rescue.fingerprint(self.case.target))
        self.assertEqual(assist.read(self.case.workspace / "result.json")["state"], "failed")
        with self.assertRaisesRegex(RuntimeError, "Previous run failed"):
            assist.wait_and_apply(self.case.workspace)

    def test_cache_inside_backup_is_rejected_before_setup(self):
        with mock.patch.object(assist, "engine_file") as setup, contextlib.redirect_stderr(io.StringIO()):
            result = assist.main(["--cache", str(self.case.source / "cache"), "inspect",
                                  "--source-home", str(self.case.source)])
        self.assertEqual(result, 1)
        setup.assert_not_called()
        self.assertFalse((self.case.source / "cache").exists())

    def test_guard_requires_ten_continuous_quiet_seconds(self):
        ticks = [0]
        calls = []
        def clock():
            return ticks[0]
        def sleep(seconds):
            ticks[0] += seconds
        def guard():
            calls.append(ticks[0])
            if ticks[0] in (0, 5):
                raise RuntimeError("Close Codex/ChatGPT synthetic client")
        assist.wait_for_closed(guard, clock=clock, sleep=sleep)
        self.assertEqual(ticks[0], 16)
        self.assertEqual(calls[-1], 16)

    def test_unknown_guard_failure_is_not_treated_as_a_busy_client(self):
        with self.assertRaisesRegex(RuntimeError, "enumeration"):
            assist.wait_for_closed(mock.Mock(side_effect=RuntimeError("Process enumeration failed")))

    def test_standalone_download_is_pinned_and_tampering_is_rejected(self):
        content = Path(rescue.__file__).read_bytes()
        fake_location = self.case.root / "standalone/skill/scripts/assist.py"
        with mock.patch.object(assist, "__file__", str(fake_location)), \
                mock.patch.object(assist.urllib.request, "urlopen", return_value=io.BytesIO(content)):
            path = assist.engine_file(self.cache)
        self.assertEqual(assist.sha256(path), assist.ENGINE_SHA256)
        path.write_bytes(b"synthetic tampering")
        with mock.patch.object(assist, "__file__", str(fake_location)), \
                mock.patch.object(assist.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(RuntimeError, "Cached engine changed"):
                assist.engine_file(self.cache)
            network.assert_not_called()

    def test_bad_download_is_not_installed_and_offline_never_downloads(self):
        fake_location = self.case.root / "standalone/skill/scripts/assist.py"
        with mock.patch.object(assist, "__file__", str(fake_location)), \
                mock.patch.object(assist.urllib.request, "urlopen", return_value=io.BytesIO(b"bad")):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                assist.engine_file(self.cache)
        self.assertFalse(any(self.cache.rglob("rescue.py")))
        with mock.patch.object(assist, "__file__", str(fake_location)), \
                mock.patch.object(assist.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(RuntimeError, "Offline mode"):
                assist.engine_file(self.cache, offline=True)
            network.assert_not_called()

    def test_portable_engine_and_runtime_use_bundled_files(self):
        bundle = self.case.root / "bundle"
        bundle.mkdir()
        engine = bundle / "rescue.py"
        engine.write_text("# synthetic bundled engine\n", encoding="utf-8")
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "_MEIPASS", str(bundle), create=True):
            self.assertEqual(assist.engine_file(self.cache, offline=True), engine)
            self.assertEqual(assist.runtime(self.cache, offline=True), Path(sys.executable).resolve())
        self.assertFalse(self.cache.exists())

    def test_portable_prepare_copies_the_executable_for_independent_handoff(self):
        bundle = self.case.root / "bundle"
        bundle.mkdir()
        engine = bundle / "rescue.py"
        engine.write_text("# synthetic bundled engine\n", encoding="utf-8")
        executable = self.case.root / "Codex PE Rescue.exe"
        executable.write_bytes(b"synthetic executable")
        report = {"selected_threads": 1, "selected_projects": 1}

        def engine_result(python, engine, arguments):
            if arguments[0] == "prepare":
                self.case.workspace.mkdir()
                return report
            return {"verified": True}

        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "_MEIPASS", str(bundle), create=True), \
                mock.patch.object(sys, "executable", str(executable)), \
                mock.patch.object(assist, "run_engine", side_effect=engine_result):
            result = assist.prepare_recovery(
                self.case.source, self.case.target, ["source-project"], [],
                [(fixtures.OLD_ROOT, str(self.case.project))], self.case.workspace,
                executable, engine, self.cache)
        self.assertEqual((self.case.workspace / "run-recovery.exe").read_bytes(), executable.read_bytes())
        handoff = assist.read(self.case.workspace / "handoff.json")
        self.assertTrue(handoff["portable"])
        launcher = Path(result["launcher"]).read_text(encoding="utf-8")
        self.assertIn('run-recovery.exe" wait --workspace', launcher)
        self.assertNotIn("python.exe", launcher.lower())

    def test_subprocess_inspection_filters_synthetic_titles(self):
        process = subprocess.run([sys.executable, str(HELPER), "--cache", str(self.cache), "inspect",
                                  "--source-home", str(self.case.source), "--query", "lesson"],
                                 capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual({r["id"] for r in result["threads"]}, {fixtures.MAIN, fixtures.UNRELATED})

    def test_batch_quotes_percent_paths_and_rejects_command_breaks(self):
        self.assertEqual(assist.batch_arg(r"C:\example %name% & more!\tool.py"),
                         '"C:\\example %%name%% & more!\\tool.py"')
        for value in ('bad"path', "bad\ncommand"):
            with self.assertRaises(RuntimeError):
                assist.batch_arg(value)


if __name__ == "__main__":
    unittest.main()
