"""Regression checks for recoverable writes and the legacy Markdown contract."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import workspace_io as IO
import init_research_workspace as INIT
from test_init_research_workspace import plan


class WorkspaceIOTests(unittest.TestCase):
    def pair(self, root):
        research = root / "research"
        research.mkdir()
        first, second = research / "PLAN.md", research / "STATUS.md"
        first.write_text("old plan\n", encoding="utf-8")
        second.write_text("old status\n", encoding="utf-8")
        return first, second

    def test_success_validates_written_pair_and_preserves_mode(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            a.chmod(0o640)
            expected = {a: IO.hash_file(a), b: IO.hash_file(b)}
            def validate():
                self.assertEqual(a.read_text(), "new plan")
                self.assertEqual(b.read_text(), "new status")
                self.assertTrue(IO.pending_transaction(root))
            with IO.WorkspaceLock(root):
                IO.commit_files(root, {a: "new plan", b: "new status"}, expected, validate)
            self.assertFalse(IO.pending_transaction(root))
            self.assertEqual(a.stat().st_mode & 0o777, 0o640)
            self.assertTrue((root / IO.LOCK_NAME).is_file())

    def test_stale_hash_and_absence_assertion_do_not_write(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            for expected in ({a: "0" * 64}, {a: None}):
                with self.subTest(expected=expected), IO.WorkspaceLock(root):
                    with self.assertRaises(IO.ConflictError):
                        IO.commit_files(root, {a: "replacement"}, expected)
            self.assertEqual(a.read_text(), "old plan\n")
            self.assertEqual(b.read_text(), "old status\n")
            self.assertFalse(IO.pending_transaction(root))

    def test_read_dependency_hash_is_checked_and_write_requires_expected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            with IO.WorkspaceLock(root):
                with self.assertRaises(IO.ConflictError):
                    IO.commit_files(root, {b: "new"}, {a: "0" * 64, b: IO.hash_file(b)})
                with self.assertRaises(IO.WorkspaceIOError):
                    IO.commit_files(root, {b: "new"}, {a: IO.hash_file(a)})
            self.assertEqual(b.read_text(), "old status\n")

    def test_keyboard_interrupt_restores_both_original_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            original = IO._replace
            def interrupt(source, destination):
                if source.name == "1.tmp":
                    raise KeyboardInterrupt("interrupted second replacement")
                original(source, destination)
            with IO.WorkspaceLock(root), mock.patch.object(IO, "_replace", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    IO.commit_files(root, {a: "new plan", b: "new status"}, {a: IO.hash_file(a), b: IO.hash_file(b)})
            self.assertEqual(a.read_text(), "old plan\n")
            self.assertEqual(b.read_text(), "old status\n")
            self.assertFalse(IO.pending_transaction(root))

    def test_validation_error_restores_originals_and_removes_new_checkpoint(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            checkpoint = root / "research/records/checkpoints/one.md"
            def reject():
                raise ValueError("invalid state")
            with IO.WorkspaceLock(root):
                with self.assertRaisesRegex(ValueError, "invalid state"):
                    IO.commit_files(root, {b: "new", checkpoint: "record"}, {a: IO.hash_file(a), b: IO.hash_file(b), checkpoint: None}, reject)
            self.assertEqual(a.read_text(), "old plan\n")
            self.assertEqual(b.read_text(), "old status\n")
            self.assertFalse(checkpoint.exists())
            self.assertFalse(IO.pending_transaction(root))

    def interrupted_process(self, root):
        # Abrupt process death cannot run Python finally/except handlers.
        code = '''
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import workspace_io as w
root = Path(sys.argv[2]); a=root/'research/PLAN.md'; b=root/'research/STATUS.md'
original=w._replace
def crash(source, destination):
    if source.name == '1.tmp': os._exit(73)
    original(source,destination)
w._replace=crash
with w.WorkspaceLock(root):
    w.commit_files(root,{a:'new plan', b:'new status'},{a:w.hash_file(a),b:w.hash_file(b)})
'''
        child = subprocess.run([sys.executable, "-B", "-c", code, str(ROOT / "scripts"), str(root)], capture_output=True)
        self.assertEqual(child.returncode, 73, child.stderr)

    def test_hard_exit_leaves_marker_refuses_new_write_and_recovers(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            self.interrupted_process(root)
            self.assertEqual(a.read_text(), "new plan")
            self.assertEqual(b.read_text(), "old status\n")
            self.assertTrue(IO.pending_transaction(root))
            with IO.WorkspaceLock(root):
                with self.assertRaises(IO.PendingTransactionError):
                    IO.commit_files(root, {a: "third"}, {a: IO.hash_file(a)})
                self.assertTrue(IO.recover(root))
                self.assertFalse(IO.recover(root))
            self.assertEqual(a.read_text(), "old plan\n")
            self.assertEqual(b.read_text(), "old status\n")
            self.assertFalse(IO.pending_transaction(root))

    def test_recovery_preserves_intervening_user_change_and_backups(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            self.interrupted_process(root)
            a.write_text("new user work")
            with IO.WorkspaceLock(root):
                with self.assertRaises(IO.ConflictError):
                    IO.recover(root)
            self.assertEqual(a.read_text(), "new user work")
            tx = root / IO.TRANSACTION_NAME
            self.assertEqual((tx / "0.bak").read_text(), "old plan\n")
            self.assertEqual((tx / "1.bak").read_text(), "old status\n")

    def test_failed_rollback_preserves_backups_for_later_recovery(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            original = IO._replace
            def fail(source, destination):
                if source.name == "1.tmp" or ".restore." in source.name:
                    raise OSError("simulated I/O failure")
                original(source, destination)
            with IO.WorkspaceLock(root):
                with mock.patch.object(IO, "_replace", side_effect=fail):
                    with self.assertRaisesRegex(IO.WorkspaceIOError, "backups retained"):
                        IO.commit_files(root, {a: "new plan", b: "new status"}, {a: IO.hash_file(a), b: IO.hash_file(b)})
                self.assertTrue(IO.pending_transaction(root))
                self.assertTrue(IO.recover(root))
            self.assertEqual(a.read_text(), "old plan\n")
            self.assertEqual(b.read_text(), "old status\n")

    def test_cleanup_interruption_keeps_committed_pair(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            with IO.WorkspaceLock(root):
                with mock.patch.object(IO, "_cleanup", side_effect=OSError("cleanup interrupted")):
                    with self.assertRaises(OSError):
                        IO.commit_files(root, {a: "new plan", b: "new status"}, {a: IO.hash_file(a), b: IO.hash_file(b)})
                self.assertTrue(IO.pending_transaction(root))
                self.assertTrue(IO.recover(root))
            self.assertEqual(a.read_text(), "new plan")
            self.assertEqual(b.read_text(), "new status")

    def test_rollback_cleanup_can_be_interrupted_repeatedly_after_backup_deletion(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            tx = root / IO.TRANSACTION_NAME
            def reject():
                raise ValueError("invalid state")
            def delete_backup_then_interrupt(index):
                def cleanup(root, tx):
                    (tx / f"{index}.bak").unlink()
                    raise OSError("cleanup interrupted after deleting a backup")
                return cleanup
            with IO.WorkspaceLock(root):
                with mock.patch.object(IO, "_cleanup", side_effect=delete_backup_then_interrupt(0)):
                    with self.assertRaisesRegex(IO.WorkspaceIOError, "recovery required"):
                        IO.commit_files(root, {a: "new plan", b: "new status"}, {a: IO.hash_file(a), b: IO.hash_file(b)}, reject)
                self.assertEqual(a.read_text(), "old plan\n")
                self.assertEqual(b.read_text(), "old status\n")
                self.assertTrue(IO.pending_transaction(root))
                with mock.patch.object(IO, "_cleanup", side_effect=delete_backup_then_interrupt(1)):
                    with self.assertRaisesRegex(OSError, "cleanup interrupted"):
                        IO.recover(root)
                self.assertTrue(IO.pending_transaction(root))
                self.assertTrue(IO.recover(root))
                self.assertFalse(IO.recover(root))
            self.assertEqual(a.read_text(), "old plan\n")
            self.assertEqual(b.read_text(), "old status\n")

    def test_partial_rollback_needs_only_unrestored_targets_backups(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            tx = root / IO.TRANSACTION_NAME
            original = IO._replace
            def interrupt_second_restore(source, destination):
                if source.name == "1.restore.tmp":
                    raise OSError("second restore interrupted")
                original(source, destination)
            def reject():
                raise ValueError("invalid state")
            with IO.WorkspaceLock(root):
                with mock.patch.object(IO, "_replace", side_effect=interrupt_second_restore):
                    with self.assertRaisesRegex(IO.WorkspaceIOError, "recovery required"):
                        IO.commit_files(root, {a: "new plan", b: "new status"}, {a: IO.hash_file(a), b: IO.hash_file(b)}, reject)
                self.assertEqual(a.read_text(), "old plan\n")
                self.assertEqual(b.read_text(), "new status")
                (tx / "0.bak").unlink()
                self.assertTrue(IO.recover(root))
            self.assertEqual(a.read_text(), "old plan\n")
            self.assertEqual(b.read_text(), "old status\n")
            self.assertFalse(IO.pending_transaction(root))

    def test_missing_or_corrupt_needed_backup_refuses_recovery_before_writing(self):
        for damage in ("missing", "corrupt"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as raw:
                root = Path(raw); a, b = self.pair(root)
                self.interrupted_process(root)
                tx = root / IO.TRANSACTION_NAME
                # The second destination is already original; its backup is
                # unnecessary. The first still needs a valid restore source.
                (tx / "1.bak").unlink()
                backup = tx / "0.bak"
                if damage == "missing":
                    backup.unlink()
                else:
                    backup.write_text("damaged backup")
                with IO.WorkspaceLock(root):
                    with self.assertRaisesRegex(IO.WorkspaceIOError, "backup missing or corrupt"):
                        IO.recover(root)
                self.assertEqual(a.read_text(), "new plan")
                self.assertEqual(b.read_text(), "old status\n")
                self.assertTrue(IO.pending_transaction(root))

    def test_recovery_after_cleanup_interruption_preserves_later_user_changes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            tx = root / IO.TRANSACTION_NAME
            def reject():
                raise ValueError("invalid state")
            def cleanup(root, tx):
                (tx / "0.bak").unlink()
                (tx / "1.bak").unlink()
                raise OSError("cleanup interrupted")
            with IO.WorkspaceLock(root):
                with mock.patch.object(IO, "_cleanup", side_effect=cleanup):
                    with self.assertRaises(IO.WorkspaceIOError):
                        IO.commit_files(root, {a: "new plan", b: "new status"}, {a: IO.hash_file(a), b: IO.hash_file(b)}, reject)
                a.write_text("later user work")
                with self.assertRaises(IO.ConflictError):
                    IO.recover(root)
            self.assertEqual(a.read_text(), "later user work")
            self.assertEqual(b.read_text(), "old status\n")
            self.assertTrue(IO.pending_transaction(root))

    def test_lock_rejects_another_writer_and_releases_after_exception(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with self.assertRaisesRegex(RuntimeError, "caller failed"):
                with IO.WorkspaceLock(root):
                    with self.assertRaises(IO.WorkspaceIOError):
                        with IO.WorkspaceLock(root):
                            pass
                    raise RuntimeError("caller failed")
            with IO.WorkspaceLock(root):
                pass

    def test_output_symlink_escape_and_special_target_are_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "workspace"; outside = Path(raw) / "outside"
            root.mkdir(); outside.mkdir()
            (root / "research").symlink_to(outside, target_is_directory=True)
            target = root / "research/PLAN.md"
            with IO.WorkspaceLock(root):
                with self.assertRaises(IO.WorkspaceIOError):
                    IO.commit_files(root, {target: "new"}, {target: None})
            self.assertEqual(list(outside.iterdir()), [])
            (root / "research").unlink(); (root / "research").mkdir()
            target.mkdir()
            with self.assertRaises(IO.WorkspaceIOError):
                IO.ensure_within(root, target)
            target.rmdir(); target.symlink_to(outside / "absent.md")
            with self.assertRaises(IO.WorkspaceIOError):
                IO.ensure_within(root, target)

    def test_invalid_recovery_manifest_cannot_write_outside_root(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            self.interrupted_process(root)
            manifest = root / IO.TRANSACTION_NAME / "manifest.json"
            value = json.loads(manifest.read_text())
            value["entries"][0]["path"] = "../outside.md"
            manifest.write_text(json.dumps(value))
            with IO.WorkspaceLock(root):
                with self.assertRaises(IO.WorkspaceIOError):
                    IO.recover(root)
            self.assertTrue(IO.pending_transaction(root))

    def test_interrupted_preparation_does_not_touch_destinations(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); a, b = self.pair(root)
            tx = root / IO.TRANSACTION_NAME; tx.mkdir()
            (tx / "0.bak").write_text("old plan\n")
            (tx / "0.tmp").write_text("new plan")
            with IO.WorkspaceLock(root):
                self.assertTrue(IO.recover(root))
            self.assertEqual(a.read_text(), "old plan\n")
            self.assertEqual(b.read_text(), "old status\n")


class LegacyContractRegressionTests(unittest.TestCase):
    def test_legacy_cli_refuses_symlink_before_writing(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)/"workspace"; outside = Path(raw)/"outside"
            root.mkdir(); outside.mkdir()
            (root/"research").symlink_to(outside, target_is_directory=True)
            process = subprocess.run([sys.executable, "-B", str(ROOT/"scripts/init_research_workspace.py"), "--workspace-root", str(root), "--plan-file", "-", "--json"], input=json.dumps(plan()), text=True, capture_output=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("escapes workspace", process.stdout)
            self.assertEqual(list(outside.iterdir()), [])

    def test_markdown_invariants_survive_both_localizations(self):
        for language in ("zh", "en"):
            with self.subTest(language=language):
                original = INIT.render_plan(plan(), language, "2026-09-22", 1)
                status = INIT.render_status(plan(), language, "2026-09-22", 1)
                acceptance = "验收" if language == "zh" else "acceptance"
                inner = "范围内" if language == "zh" else "In"
                milestone = f"- M1 - Working CLI ({acceptance}: Tests pass)"
                cases = [
                    original.replace("\nREADY\n", "\nNOT_READY\n"),
                    original.replace(f"({acceptance}: Tests pass)", f"({acceptance}: )"),
                    original.replace(milestone, milestone+"\n"+milestone),
                    original.replace(f"### {inner}", "### Broken"),
                    original.replace("- implementation", ""),
                ]
                self.assertEqual(INIT.validate_v2_content(original, status), [])
                for damaged in cases:
                    self.assertTrue(INIT.validate_v2_content(damaged, status))

    def test_legacy_library_interrupt_wrapper_preserves_pair(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); research = root/"research"; research.mkdir()
            a, b = research/"PLAN.md", research/"STATUS.md"
            a.write_text("original plan"); b.write_text("original status")
            original = INIT._replace
            def interrupt(source, destination):
                if source.name == "1.tmp":
                    raise KeyboardInterrupt()
                original(source, destination)
            with mock.patch.object(INIT, "_replace", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    INIT.commit_core_files({a: "new plan", b: "new status"}, overwrite=True)
            self.assertEqual(a.read_text(), "original plan")
            self.assertEqual(b.read_text(), "original status")
            self.assertFalse(IO.pending_transaction(root))

    def test_dry_run_and_validation_create_no_runtime_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            process = subprocess.run([sys.executable, "-B", str(ROOT/"scripts/init_research_workspace.py"), "--workspace-root", str(root), "--plan-file", "-", "--dry-run"], input=json.dumps(plan()), text=True, capture_output=True)
            self.assertEqual(process.returncode, 0, process.stdout+process.stderr)
            self.assertEqual(list(root.iterdir()), [])
            process = subprocess.run([sys.executable, "-B", str(ROOT/"scripts/init_research_workspace.py"), "--workspace-root", str(root), "--validate-only"], text=True, capture_output=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
