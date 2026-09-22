"""Regression cases from a second review of real project-continuity flows."""

import copy
import hashlib
import json
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

import test_project_state as fixtures

sys.path.insert(0, str(fixtures.ROOT / "scripts"))
import project_state as ps
import workspace_io as io


class ReviewRegressionTests(unittest.TestCase):
    # Reuse fixture helpers without inheriting and running the original suite twice.
    for _name in (
        "setUp", "input_json", "run_cli", "assert_success", "assert_failure", "snapshot",
        "resume", "initialize", "expected_arguments", "update", "checkpoint", "evidence",
        "accepted_milestone", "progressing_state",
    ):
        locals()[_name] = getattr(fixtures.ProjectStateCLITests, _name)
    del _name

    def advancing_workspace(self):
        initial = self.initialize()
        state = self.progressing_state(initial)
        state["next_action"] = "Implement the now-cancelled M2 conversion"
        self.assert_success(self.checkpoint(self.update(state, "conversion-running"), initial))
        return self.resume()

    def refreeze(self, replacement, previous, identifier="revise-plan", *extra):
        return self.run_cli(
            "refreeze", "--plan-file", self.input_json(replacement), "--id", identifier,
            "--summary", "Apply the reviewed replacement milestone plan",
            *extra, *self.expected_arguments(previous),
        )

    def without_current_milestone(self):
        replacement = fixtures.plan()
        replacement["milestones"] = [m for m in replacement["milestones"] if m["id"] != "M2"]
        return replacement

    def test_removing_current_milestone_requires_replacement_action_without_writes(self):
        current = self.advancing_workspace()
        before = self.snapshot()
        result = self.refreeze(self.without_current_milestone(), current)
        self.assert_failure(result)
        self.assertIn("next", json.loads(result.stderr)["message"].lower())
        self.assertEqual(self.snapshot(), before)

    def test_explicit_action_replaces_cancelled_work_and_is_part_of_replay_identity(self):
        current = self.advancing_workspace()
        replacement = self.without_current_milestone()
        action = "Begin the retained M3 storage work"
        self.assert_success(self.refreeze(replacement, current, "cancel-conversion", "--next-action", action))
        actual = self.resume()
        self.assertEqual(actual["status"]["current_milestone"], "M3")
        self.assertEqual(actual["status"]["next_action"], action)
        after = self.snapshot()
        self.assert_success(self.refreeze(replacement, current, "cancel-conversion", "--next-action", action))
        self.assertEqual(self.snapshot(), after)
        self.assert_failure(self.refreeze(replacement, actual, "cancel-conversion", "--next-action", "A conflicting replacement action"))
        self.assertEqual(self.snapshot(), after)

    def test_changed_plan_action_replaces_cancelled_work_without_extra_argument(self):
        current = self.advancing_workspace()
        replacement = self.without_current_milestone()
        replacement["next_action"] = "Implement the retained storage stage"
        self.assert_success(self.refreeze(replacement, current))
        self.assertEqual(self.resume()["status"]["next_action"], replacement["next_action"])

    def test_later_stage_change_preserves_current_dynamic_next_action(self):
        current = self.advancing_workspace()
        replacement = fixtures.plan()
        replacement["milestones"][2]["acceptance"] = ["Storage preserves the accepted converted fields"]
        self.assert_success(self.refreeze(replacement, current))
        actual = self.resume()["status"]
        self.assertEqual(actual["current_milestone"], "M2")
        self.assertEqual(actual["next_action"], current["status"]["next_action"])

    def test_reselecting_after_accepted_current_milestone_requires_valid_next_action(self):
        current = self.advancing_workspace()
        finished = copy.deepcopy(current["status"])
        self.accepted_milestone(finished["milestones"][1], finished["evidence"][0]["id"])
        finished["next_action"] = "Report that the current conversion stage is accepted"
        self.assert_success(self.checkpoint(self.update(finished, "conversion-accepted"), current))
        current = self.resume()
        replacement = fixtures.plan()
        replacement["milestones"][2]["acceptance"] = ["Storage preserves the accepted converted fields"]
        before = self.snapshot()
        self.assert_failure(self.refreeze(replacement, current))
        self.assertEqual(self.snapshot(), before)
        self.assert_success(self.refreeze(replacement, current, "next-storage", "--next-action", "Implement M3 storage"))
        actual = self.resume()["status"]
        self.assertEqual(actual["current_milestone"], "M3")
        self.assertEqual(actual["next_action"], "Implement M3 storage")

    def test_refreeze_archives_supported_conclusion_when_changed_or_removed(self):
        for operation in ("change", "remove"):
            with self.subTest(operation=operation):
                self.workspace = self.base / operation
                self.workspace.mkdir()
                current = self.advancing_workspace()
                replacement = fixtures.plan()
                if operation == "change":
                    replacement["milestones"][0]["acceptance"] = ["New scientific check passes"]
                else:
                    replacement["milestones"] = replacement["milestones"][1:]
                self.assert_success(self.refreeze(replacement, current, operation + "-scientific-check"))
                records = list((self.workspace / "research/records/checkpoints").glob("*scientific-check.md"))
                self.assertEqual(len(records), 1)
                prior_row = next(line for line in records[0].read_text(encoding="utf-8").splitlines() if "Previous M1:" in line)
                self.assertIn("conclusion=supported", prior_row)
                self.assertIn("evidence=ingestion-check", prior_row)
                self.assertIn("source_plan_hash: " + current["hashes"]["plan"], records[0].read_text(encoding="utf-8"))
                archived = records[0].read_text(encoding="utf-8")
                self.assertIn("ingestion-check [observed] docs/ingestion-check.txt | code=fixture-code-revision | checked=2026-05-12", archived)
                state = self.resume()["status"]
                if operation == "change":
                    self.assertEqual(state["milestones"][0]["conclusion"], "unverified")
                else:
                    self.assertNotIn("M1", [m["id"] for m in state["milestones"]])

    def test_reader_rejects_transient_status_after_real_writer_rollback(self):
        self.assert_reader_rejects_transient_bytes_after_rollback("status")

    def test_reader_rejects_transient_plan_after_real_writer_rollback(self):
        self.assert_reader_rejects_transient_bytes_after_rollback("plan")

    def assert_reader_rejects_transient_bytes_after_rollback(self, target):
        self.initialize()
        root = self.workspace
        pp, sp = ps.paths(root)
        before = ps.read_workspace(root)
        newer = copy.deepcopy(before["status"])
        newer["summary"] = "Transient progress from a transaction which will fail"
        newer["next_action"] = "Do not act on this uncommitted progress"
        changed_path = {"plan": pp, "status": sp}[target]
        replacement = ps.render_status(newer, 1, 2, "2026-05-12") if target == "status" else before["plan_text"].replace(
            fixtures.plan()["goal"], "A transient, uncommitted project goal",
        )
        self.assertNotEqual(replacement, before[target + "_text"])
        reader_ready, writer_staged = threading.Event(), threading.Event()
        reader_consumed, rollback_done = threading.Event(), threading.Event()
        real_text, real_bytes, real_hash = Path.read_text, Path.read_bytes, io.hash_file
        reading_hash = False
        intercepted = False
        writer_errors = []

        def checked_wait(event):
            if not event.wait(10):
                raise AssertionError("transaction race fixture timed out")

        def tracked_hash(path):
            nonlocal reading_hash
            if threading.current_thread() is threading.main_thread():
                reading_hash = True
                try:
                    return real_hash(path)
                finally:
                    reading_hash = False
            return real_hash(path)

        def interleaved_read(original, path, *args, **kwargs):
            nonlocal intercepted
            if path == changed_path and threading.current_thread() is threading.main_thread() and not reading_hash and not intercepted:
                intercepted = True
                reader_ready.set()
                checked_wait(writer_staged)
                value = original(path, *args, **kwargs)
                reader_consumed.set()
                checked_wait(rollback_done)
                return value
            return original(path, *args, **kwargs)

        def writer():
            try:
                checked_wait(reader_ready)

                def fail_validation():
                    writer_staged.set()
                    checked_wait(reader_consumed)
                    raise OSError("Simulated validation failure after writing " + target)

                with io.WorkspaceLock(root):
                    try:
                        io.commit_files(root, {changed_path: replacement}, {pp: before["hashes"]["plan"], sp: before["hashes"]["status"]}, fail_validation)
                    except OSError as exc:
                        if "Simulated validation failure" not in str(exc):
                            raise
            except BaseException as exc:
                writer_errors.append(exc)
            finally:
                rollback_done.set()

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        try:
            with mock.patch.object(io, "hash_file", tracked_hash), \
                 mock.patch.object(Path, "read_text", lambda path, *a, **k: interleaved_read(real_text, path, *a, **k)), \
                 mock.patch.object(Path, "read_bytes", lambda path: interleaved_read(real_bytes, path)):
                with self.assertRaises(ps.Error):
                    ps.read_workspace(root)
        finally:
            reader_ready.set()
            reader_consumed.set()
            thread.join(timeout=12)
        self.assertFalse(thread.is_alive())
        self.assertFalse(writer_errors, writer_errors)
        self.assertTrue(intercepted, "fixture must actually expose the transient " + target + " bytes")
        self.assertFalse(io.pending_transaction(root))
        actual = ps.read_workspace(root)
        self.assertEqual(actual["hashes"], before["hashes"])
        self.assertEqual(actual["status_revision"], 1)

    def test_crlf_snapshots_keep_exact_file_hashes_and_allow_checkpoint(self):
        self.initialize()
        for path in ps.paths(self.workspace):
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        before = self.snapshot()
        current = self.resume()
        for name, path in zip(("plan", "status"), ps.paths(self.workspace)):
            self.assertEqual(current["hashes"][name], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(self.snapshot(), before)
        updated = copy.deepcopy(current["status"])
        updated["summary"] = "A newly confirmed fact after reading CRLF files"
        self.assert_success(self.checkpoint(self.update(updated, "crlf-checkpoint"), current))
        self.assertEqual(self.resume()["status"], updated)

    def test_directory_replacing_old_reference_is_warned_and_can_be_removed(self):
        initial = self.initialize()
        reference = self.workspace / "docs/obsolete-report.txt"
        reference.parent.mkdir()
        reference.write_text("A report that was formerly required\n", encoding="utf-8")
        state = copy.deepcopy(initial["status"])
        state["must_read"].append("docs/obsolete-report.txt")
        self.assert_success(self.checkpoint(self.update(state, "report-added"), initial))
        reference.unlink()
        reference.mkdir()
        before = self.snapshot()
        current = self.resume()
        self.assertTrue(any("docs/obsolete-report.txt" in warning for warning in current["warnings"]))
        self.assertEqual(self.snapshot(), before)
        self.assert_failure(self.run_cli("validate"))
        corrected = copy.deepcopy(current["status"])
        corrected["must_read"].remove("docs/obsolete-report.txt")
        corrected["summary"] = "The obsolete must-read report was removed after becoming unavailable"
        self.assert_success(self.checkpoint(self.update(corrected, "report-removed"), current))
        self.assert_success(self.run_cli("validate"))
        self.assertTrue(reference.is_dir())

    def test_new_required_reference_must_still_be_an_existing_regular_file(self):
        current = self.initialize()
        directory = self.workspace / "docs/report"
        directory.mkdir(parents=True)
        for reference in ("docs/report", "docs/missing.txt"):
            with self.subTest(reference=reference):
                bad = copy.deepcopy(current["status"])
                bad["must_read"].append(reference)
                before = self.snapshot()
                self.assert_failure(self.checkpoint(self.update(bad), current))
                self.assertEqual(self.snapshot(), before)

    def test_tolerant_resume_does_not_follow_reference_symlink_outside_workspace(self):
        initial = self.initialize()
        ref = self.workspace / "docs/report.txt"
        ref.parent.mkdir()
        ref.write_text("Initially valid report\n", encoding="utf-8")
        state = copy.deepcopy(initial["status"])
        state["must_read"].append("docs/report.txt")
        self.assert_success(self.checkpoint(self.update(state, "safe-reference"), initial))
        outside = self.base / "outside-secret.txt"
        outside.write_text("Not an allowed project reference", encoding="utf-8")
        ref.unlink()
        try:
            ref.symlink_to(outside)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest(f"symbolic-link safety test requires symlink permission: {exc}")
            raise
        before = self.snapshot()
        result = self.run_cli("resume")
        self.assert_failure(result)
        self.assertNotIn(outside.read_text(encoding="utf-8"), result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)

    def initialize_legacy_missing_reference(self):
        result = subprocess.run(
            [sys.executable, str(fixtures.LEGACY_INIT), "--workspace-root", str(self.workspace), "--plan-file", str(self.input_json(fixtures.plan()))],
            capture_output=True, text=True, check=False,
        )
        self.assert_success(result)
        sp = self.workspace / "research/STATUS.md"
        sp.write_text(sp.read_text(encoding="utf-8") + "- docs/lost-report.txt\n", encoding="utf-8")

    def test_legacy_missing_reference_can_be_previewed_and_migrated_with_reviewed_state(self):
        self.initialize_legacy_missing_reference()
        before = self.snapshot()
        current = self.resume()
        self.assertTrue(any("docs/lost-report.txt" in warning for warning in current["warnings"]))
        self.assert_failure(self.run_cli("validate"))
        self.assert_success(self.run_cli("enable-tracking"))
        corrected = ps.initial_state(fixtures.plan())
        corrected["summary"] = "Legacy state reviewed; unavailable report is no longer required"
        corrected_path = self.input_json(corrected)
        tracking_authorization = "User authorized key-event tracking for the reviewed legacy migration only."
        tracking_coordinator = "Legacy migration coordinator"
        tracking_arguments = ["--authorization", tracking_authorization, "--coordinator", tracking_coordinator]
        expected = copy.deepcopy(corrected)
        expected["authorization"] += [tracking_authorization, "Coordinator: " + tracking_coordinator]
        preview = self.run_cli("enable-tracking", "--status-file", corrected_path, *tracking_arguments)
        self.assert_success(preview)
        self.assertEqual(self.snapshot(), before)
        self.assert_success(self.run_cli("enable-tracking", "--apply", "--status-file", corrected_path, *tracking_arguments, *self.expected_arguments(current)))
        migrated = self.resume()
        self.assertEqual(migrated["format"], ps.FORMAT)
        self.assertEqual(migrated["status"], expected)
        self.assert_success(self.run_cli("validate"))
        self.assertIn(before["research/STATUS.md"], self.snapshot().values())

    def test_legacy_migration_rejects_missing_reference_in_replacement_state(self):
        self.initialize_legacy_missing_reference()
        current = self.resume()
        invalid = ps.initial_state(fixtures.plan())
        invalid["must_read"].append("docs/lost-report.txt")
        invalid_path = self.input_json(invalid)
        before = self.snapshot()
        self.assert_failure(self.run_cli("enable-tracking", "--status-file", invalid_path))
        self.assert_failure(self.run_cli("enable-tracking", "--apply", "--status-file", invalid_path, *self.expected_arguments(current)))
        self.assertEqual(self.snapshot(), before)

    def test_legacy_reference_lists_keep_blank_line_compatibility_without_writes(self):
        for language in ("zh", "en"):
            with self.subTest(language=language):
                root = self.base / ("legacy-blank-lines-" + language)
                (root / "research").mkdir(parents=True)
                (root / "report.md").write_text("A current project report\n", encoding="utf-8")
                (root / "research/PLAN.md").write_text(ps.legacy.render_plan(fixtures.plan(), language, "2026-05-12", 1), encoding="utf-8")
                (root / "research/STATUS.md").write_text(ps.legacy.render_status(
                    fixtures.plan(), language, "2026-05-12", 1,
                    preserved_must_read="- research/PLAN.md\n\n \t\n- report.md",
                ), encoding="utf-8")
                self.assertEqual(ps.legacy.validate_v2(root), [], "fixture must remain valid under the legacy contract")
                before = self.snapshot(root)
                current = self.resume(root)
                self.assertEqual(current["format"], "plan-your-project/v2")
                self.assertIsNone(current["status"])
                self.assert_success(self.run_cli("validate", workspace=root))
                self.assert_success(self.run_cli("enable-tracking", workspace=root))
                self.assertEqual(self.snapshot(root), before)

    def test_legacy_reference_lists_still_reject_malformed_entries(self):
        for index, entry in enumerate(("report.md", "- report.md ", "  - report.md")):
            with self.subTest(entry=entry):
                root = self.base / ("legacy-invalid-list-" + str(index))
                (root / "research").mkdir(parents=True)
                for name in ("report.md", "report.md "):
                    (root / name).write_text("An existing file cannot legitimize an invalid list item\n", encoding="utf-8")
                (root / "research/PLAN.md").write_text(ps.legacy.render_plan(fixtures.plan(), "zh", "2026-05-12", 1), encoding="utf-8")
                # Keep the malformed entry away from the section boundary so
                # section_body's ordinary outer trim cannot change its syntax.
                (root / "research/STATUS.md").write_text(ps.legacy.render_status(
                    fixtures.plan(), "zh", "2026-05-12", 1,
                    preserved_must_read="- research/PLAN.md\n\n" + entry + "\n- report.md",
                ), encoding="utf-8")
                self.assertTrue(ps.legacy.validate_v2(root), "fixture must be invalid under the legacy contract")
                before = self.snapshot(root)
                self.assert_failure(self.run_cli("resume", workspace=root))
                self.assert_failure(self.run_cli("enable-tracking", workspace=root))
                self.assertEqual(self.snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
