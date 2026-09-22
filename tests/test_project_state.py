"""CLI integration tests for durable, evidence-aware project continuity."""

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "project_state.py"
LEGACY_INIT = ROOT / "scripts" / "init_research_workspace.py"


def plan(**changes):
    value = {
        "schema_version": "2.0",
        "project_name": "连续接续测试",
        "problem": "Preserve reliable progress across independent sessions",
        "goal": "Deliver the agreed import workflow",
        "success_criteria": ["The import workflow meets its acceptance checks"],
        "scope": {"in": ["import workflow"], "out": ["unrelated services"]},
        "constraints": ["Preserve existing completed work"],
        "selected_approach": "Existing parser with a single-file store",
        "alternatives_considered": [
            {"option": "Chunked store", "tradeoffs": ["More files, bounded reads"]}
        ],
        "locked_decisions": ["Use the existing parser", "Use a single-file store"],
        "milestones": [
            {"id": "M1", "outcome": "Ingestion works", "acceptance": ["Ingestion check passes"]},
            {"id": "M2", "outcome": "Conversion works", "acceptance": ["Conversion check passes"]},
            {"id": "M3", "outcome": "Storage works", "acceptance": ["Storage check passes"]},
        ],
        "risks": [{"risk": "Stale state", "mitigation_or_validation": "Compare revisions and evidence"}],
        "assumptions": [],
        "open_questions": [],
        "evidence": [],
        "next_action": "Implement ingestion",
        "freeze_readiness": "READY",
    }
    value.update(changes)
    return value


class ProjectStateCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.inputs = self.base / "inputs"
        self.inputs.mkdir()
        self.source_number = 0

    def input_json(self, value):
        self.source_number += 1
        path = self.inputs / f"input-{self.source_number}.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def run_cli(self, command, *arguments, workspace=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), command, "--workspace-root", str(workspace or self.workspace), "--json", *map(str, arguments)],
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)

    def assert_failure(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)

    def snapshot(self, workspace=None):
        root = workspace or self.workspace
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def resume(self, workspace=None):
        result = self.run_cli("resume", workspace=workspace)
        self.assert_success(result)
        data = json.loads(result.stdout)
        self.assertTrue({"format", "plan_revision", "status_revision", "hashes", "status", "warnings", "git"} <= data.keys())
        self.assertTrue({"plan", "status"} <= data["hashes"].keys())
        return data

    def initialize(self, workspace=None):
        root = workspace or self.workspace
        root.mkdir(parents=True, exist_ok=True)
        result = self.run_cli("init", "--plan-file", self.input_json(plan()), workspace=root)
        self.assert_success(result)
        return self.resume(root)

    def expected_arguments(self, resumed):
        return ["--expected-plan-hash", resumed["hashes"]["plan"], "--expected-status-hash", resumed["hashes"]["status"]]

    def update(self, state, identifier="checkpoint-one", summary="Record verified progress"):
        return {
            "id": identifier,
            "date": "2026-05-12",
            "summary": summary,
            "changes": ["Updated the current execution facts"],
            "status": copy.deepcopy(state),
        }

    def checkpoint(self, update, resumed):
        return self.run_cli("checkpoint", "--update-file", self.input_json(update), *self.expected_arguments(resumed))

    def evidence(self, identifier="ingestion-check", source="observed", ref="docs/ingestion-check.txt"):
        path = self.workspace / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Recorded acceptance check: PASS\n", encoding="utf-8")
        return {
            "id": identifier,
            "source": source,
            "ref": ref,
            "summary": "The focused acceptance check passed",
            "code_ref": "fixture-code-revision",
            "checked_at": "2026-05-12",
        }

    def accepted_milestone(self, milestone, evidence_id):
        milestone.update(
            execution="done",
            validation="passed",
            acceptance="accepted",
            summary="Implemented and accepted against the frozen check",
            evidence=[evidence_id],
            acceptance_basis="The recorded check covers this milestone's frozen acceptance",
            conclusion="supported",
        )

    def progressing_state(self, initial):
        state = copy.deepcopy(initial["status"])
        evidence = self.evidence()
        state["evidence"] = [evidence]
        state["state"] = "in_progress"
        state["summary"] = "M1 accepted; M2 implementation is underway"
        state["current_milestone"] = "M2"
        state["next_action"] = "Finish the conversion acceptance check"
        state["authorization"] = ["The user authorized the import implementation and its progress records"]
        rows = {row["id"]: row for row in state["milestones"]}
        self.accepted_milestone(rows["M1"], evidence["id"])
        rows["M2"].update(execution="running", summary="Conversion implementation is underway")
        return state

    def test_init_resume_and_read_only_commands_preserve_all_files(self):
        initial = self.initialize()
        self.assertEqual({row["id"] for row in initial["status"]["milestones"]}, {"M1", "M2", "M3"})
        before = self.snapshot()
        for command in ("resume", "validate", "handoff", "enable-tracking"):
            with self.subTest(command=command):
                self.assert_success(self.run_cli(command))
                self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.resume()["hashes"], initial["hashes"])

    def test_checkpoint_updates_status_without_changing_plan(self):
        initial = self.initialize()
        state = self.progressing_state(initial)
        plan_bytes = (self.workspace / "research/PLAN.md").read_bytes()
        self.assert_success(self.checkpoint(self.update(state), initial))
        current = self.resume()
        self.assertEqual(current["status"], state)
        self.assertGreater(current["status_revision"], initial["status_revision"])
        self.assertEqual(current["plan_revision"], initial["plan_revision"])
        self.assertEqual((self.workspace / "research/PLAN.md").read_bytes(), plan_bytes)
        self.assert_success(self.run_cli("validate"))

    def test_replaying_an_old_identical_checkpoint_does_not_roll_back_newer_state(self):
        initial = self.initialize()
        first = self.update(self.progressing_state(initial), "first-event")
        self.assert_success(self.checkpoint(first, initial))
        after_first = self.resume()
        second_state = copy.deepcopy(after_first["status"])
        second_state["next_action"] = "Review the newly completed conversion output"
        second_state["summary"] = "A later checkpoint recorded a new next action"
        self.assert_success(self.checkpoint(self.update(second_state, "second-event"), after_first))
        current = self.resume()
        before_replay = self.snapshot()
        self.assert_success(self.checkpoint(first, initial))
        self.assertEqual(self.snapshot(), before_replay)
        replayed = self.resume()
        self.assertEqual(replayed["status"], current["status"])
        self.assertEqual(replayed["status_revision"], current["status_revision"])

    def test_same_checkpoint_id_with_different_content_is_rejected(self):
        initial = self.initialize()
        first = self.update(self.progressing_state(initial), "same-event")
        self.assert_success(self.checkpoint(first, initial))
        latest = self.resume()
        changed = copy.deepcopy(first)
        changed["summary"] = "A conflicting account of the same event"
        before = self.snapshot()
        self.assert_failure(self.checkpoint(changed, latest))
        self.assertEqual(self.snapshot(), before)

    def test_stale_status_hash_rejects_a_new_checkpoint_without_writes(self):
        initial = self.initialize()
        first = self.update(self.progressing_state(initial), "first-event")
        self.assert_success(self.checkpoint(first, initial))
        conflicting = copy.deepcopy(first)
        conflicting["id"] = "stale-writer"
        conflicting["status"]["next_action"] = "An obsolete proposed action"
        before = self.snapshot()
        self.assert_failure(self.checkpoint(conflicting, initial))
        self.assertEqual(self.snapshot(), before)

    def test_stale_plan_hash_rejects_a_new_checkpoint_without_writes(self):
        initial = self.initialize()
        stale = copy.deepcopy(initial)
        stale["hashes"]["plan"] = "0" * 64
        before = self.snapshot()
        self.assert_failure(self.checkpoint(self.update(initial["status"]), stale))
        self.assertEqual(self.snapshot(), before)

    def test_completion_without_milestone_acceptance_is_rejected(self):
        initial = self.initialize()
        state = copy.deepcopy(initial["status"])
        state["state"] = "complete"
        state["summary"] = "Claims completion without acceptance evidence"
        for milestone in state["milestones"]:
            milestone["execution"] = "done"
        before = self.snapshot()
        self.assert_failure(self.checkpoint(self.update(state), initial))
        self.assertEqual(self.snapshot(), before)

    def test_acceptance_requires_verified_evidence_and_explicit_basis(self):
        for defect in ("missing-evidence", "unverified-evidence", "missing-basis"):
            with self.subTest(defect=defect):
                root = self.base / defect
                initial = self.initialize(root)
                state = copy.deepcopy(initial["status"])
                evidence = {
                    "id": "check-one", "source": "historical", "ref": "docs/check.txt",
                    "summary": "A historical check report", "code_ref": "fixture-code-revision", "checked_at": "2026-05-12",
                }
                (root / "docs").mkdir()
                (root / "docs/check.txt").write_text("PASS\n", encoding="utf-8")
                state["evidence"] = [evidence]
                self.accepted_milestone(state["milestones"][0], evidence["id"])
                if defect == "missing-evidence":
                    state["milestones"][0]["evidence"] = []
                elif defect == "unverified-evidence":
                    evidence["source"] = "unverified"
                else:
                    state["milestones"][0]["acceptance_basis"] = ""
                before = self.snapshot(root)
                result = self.run_cli("checkpoint", "--update-file", self.input_json(self.update(state)), *self.expected_arguments(initial), workspace=root)
                self.assert_failure(result)
                self.assertEqual(self.snapshot(root), before)

    def test_missing_local_evidence_cannot_be_recorded_as_observed(self):
        initial = self.initialize()
        state = self.progressing_state(initial)
        (self.workspace / state["evidence"][0]["ref"]).unlink()
        before = self.snapshot()
        self.assert_failure(self.checkpoint(self.update(state), initial))
        self.assertEqual(self.snapshot(), before)

    def test_lost_evidence_can_be_reported_and_corrected_without_rewriting_history(self):
        initial = self.initialize()
        state = self.progressing_state(initial)
        ref = state["evidence"][0]["ref"]
        state["must_read"].append(ref)
        self.assert_success(self.checkpoint(self.update(state, "evidence-present"), initial))
        historical_records = {path: value for path, value in self.snapshot().items() if path.startswith("research/records/checkpoints/")}
        (self.workspace / ref).unlink()
        missing_snapshot = self.snapshot()
        current = self.resume()
        self.assertTrue(any(ref in warning for warning in current["warnings"]))
        self.assertEqual(current["status"]["milestones"][0]["acceptance"], "accepted")
        self.assert_failure(self.run_cli("validate"))
        handoff = self.run_cli("handoff")
        self.assert_success(handoff)
        self.assertIn(ref, handoff.stdout)
        self.assertEqual(self.snapshot(), missing_snapshot)

        corrected = copy.deepcopy(current["status"])
        corrected["evidence"][0]["source"] = "unverified"
        corrected["evidence"][0]["summary"] = "Previously reported passing evidence is now missing locally"
        corrected["must_read"].remove(ref)
        corrected["milestones"][0].update(validation="not_run", acceptance="pending", acceptance_basis="", conclusion="unverified")
        corrected["summary"] = "M1 implementation remains done, but acceptance evidence is unavailable"
        corrected["next_action"] = "Locate the original evidence before deciding whether revalidation is needed"
        self.assert_success(self.checkpoint(self.update(corrected, "evidence-now-missing"), current))
        final = self.resume()
        self.assertEqual(final["status"], corrected)
        self.assert_success(self.run_cli("validate"))
        final_files = self.snapshot()
        for path, value in historical_records.items():
            self.assertEqual(final_files[path], value)

    def test_engineering_completion_can_leave_scientific_acceptance_pending(self):
        initial = self.initialize()
        state = self.progressing_state(initial)
        milestone = next(row for row in state["milestones"] if row["id"] == "M2")
        milestone.update(
            execution="done", validation="passed", acceptance="pending",
            evidence=[state["evidence"][0]["id"]], acceptance_basis="", conclusion="unverified",
            summary="Execution passed; scientific acceptance still needs owner review",
        )
        state["next_action"] = "Review the evidence before deciding scientific acceptance"
        self.assert_success(self.checkpoint(self.update(state), initial))
        current = self.resume()["status"]
        self.assertEqual(current["state"], "in_progress")
        actual = next(row for row in current["milestones"] if row["id"] == "M2")
        self.assertEqual((actual["execution"], actual["validation"], actual["acceptance"], actual["conclusion"]), ("done", "passed", "pending", "unverified"))

    def test_validation_or_supported_conclusion_requires_evidence_even_before_acceptance(self):
        initial = self.initialize()
        for claim in ("passed", "failed", "supported"):
            with self.subTest(claim=claim):
                state = copy.deepcopy(initial["status"])
                milestone = state["milestones"][0]
                if claim == "supported":
                    milestone["conclusion"] = claim
                else:
                    milestone["validation"] = claim
                self.assertEqual(milestone["acceptance"], "pending")
                before = self.snapshot()
                self.assert_failure(self.checkpoint(self.update(state, "claim-" + claim), initial))
                self.assertEqual(self.snapshot(), before)

    def test_historical_remote_evidence_preserves_its_source_and_applicability_warning(self):
        initial = self.initialize()
        state = copy.deepcopy(initial["status"])
        state["evidence"] = [{
            "id": "reported-check", "source": "historical", "ref": "https://evidence.example/run-17",
            "summary": "An earlier report records a passing check", "code_ref": "earlier-code-revision", "checked_at": "2026-05-10",
        }]
        milestone = state["milestones"][0]
        milestone.update(execution="done", validation="passed", evidence=["reported-check"])
        self.assert_success(self.checkpoint(self.update(state), initial))
        before = self.snapshot()
        current = self.resume()
        self.assertEqual(current["status"]["evidence"][0]["source"], "historical")
        self.assertEqual(current["status"]["milestones"][0]["acceptance"], "pending")
        self.assertTrue(any("reported-check" in warning for warning in current["warnings"]))
        self.assertEqual(self.snapshot(), before)

    def test_complete_requires_no_active_blocker_or_running_task(self):
        initial = self.initialize()
        state = self.progressing_state(initial)
        for milestone in state["milestones"]:
            self.accepted_milestone(milestone, state["evidence"][0]["id"])
        state["state"] = "complete"
        state["summary"] = "All milestones accepted"
        state["next_action"] = "Archive the accepted result"
        variants = {
            "blocker": {"blockers": ["An unresolved required dependency"]},
            "running-task": {"running_tasks": [{
                "id": "still-running", "environment": "fixture execution host", "code_ref": "fixture-code-revision",
                "document_ref": "research/PLAN.md", "log": "logs/task.log", "artifacts": "outputs/task",
                "last_checked_at": "2026-05-12", "completion": "Wait for exit record and result check", "recovery": "Verify current state before resuming",
            }]},
        }
        for name, changes in variants.items():
            with self.subTest(name=name):
                invalid = copy.deepcopy(state)
                invalid.update(changes)
                before = self.snapshot()
                self.assert_failure(self.checkpoint(self.update(invalid, name), initial))
                self.assertEqual(self.snapshot(), before)
        self.assert_success(self.checkpoint(self.update(state, "all-accepted"), initial))
        self.assertEqual(self.resume()["status"]["state"], "complete")

    def test_refreeze_preserves_unaffected_progress_and_blockers(self):
        initial = self.initialize()
        state = self.progressing_state(initial)
        state["state"] = "blocked"
        state["blockers"] = ["M2 awaits a required conversion fixture"]
        rows = {row["id"]: row for row in state["milestones"]}
        self.accepted_milestone(rows["M3"], state["evidence"][0]["id"])
        self.assert_success(self.checkpoint(self.update(state), initial))
        before = self.resume()
        replacement = plan(
            selected_approach="Existing parser with a chunked store",
            alternatives_considered=[{"option": "Single-file store", "tradeoffs": ["Requires whole-file reads"]}],
            locked_decisions=["Use the existing parser", "Use a chunked store"],
        )
        result = self.run_cli(
            "refreeze", "--plan-file", self.input_json(replacement), "--affected-milestone", "M3",
            "--id", "replace-storage", "--summary", "Replace only the M3 storage decision", *self.expected_arguments(before),
        )
        self.assert_success(result)
        after = self.resume()
        self.assertEqual(after["plan_revision"], before["plan_revision"] + 1)
        self.assertEqual(after["status"]["blockers"], state["blockers"])
        self.assertEqual(after["status"]["current_milestone"], "M2")
        self.assertEqual(after["status"]["next_action"], state["next_action"])
        after_rows = {row["id"]: row for row in after["status"]["milestones"]}
        self.assertEqual(after_rows["M1"], rows["M1"])
        self.assertEqual(after_rows["M2"], rows["M2"])
        self.assertEqual(after_rows["M3"]["execution"], "done")
        self.assertEqual(after_rows["M3"]["validation"], "not_run")
        self.assertEqual(after_rows["M3"]["acceptance"], "pending")
        self.assertEqual(after_rows["M3"]["conclusion"], "unverified")
        self.assert_success(self.run_cli("validate"))

    def test_v2_enable_tracking_preview_migration_and_idempotent_entry_merge(self):
        source = self.input_json(plan())
        legacy = subprocess.run(
            [sys.executable, str(LEGACY_INIT), "--workspace-root", str(self.workspace), "--plan-file", str(source)],
            capture_output=True, text=True, check=False,
        )
        self.assert_success(legacy)
        agents = "# Existing project rules\n\nPreserve the established parser.\n"
        claude = "# Existing local instructions\n\nKeep unrelated user changes.\n"
        (self.workspace / "AGENTS.md").write_text(agents, encoding="utf-8")
        (self.workspace / "CLAUDE.md").write_text(claude, encoding="utf-8")
        agents_bytes = (self.workspace / "AGENTS.md").read_bytes()
        claude_bytes = (self.workspace / "CLAUDE.md").read_bytes()
        seed = self.initialize(self.base / "state-schema-source")
        migrated_state = self.progressing_state(seed)
        migrated_state["state"] = "blocked"
        migrated_state["blockers"] = ["M2 awaits the owner's conversion fixture"]
        legacy_status_path = self.workspace / "research/STATUS.md"
        legacy_status = legacy_status_path.read_text(encoding="utf-8")
        legacy_status = legacy_status.replace("state: planned", "state: blocked")
        legacy_status = legacy_status.replace("current_milestone: M1", "current_milestone: M2")
        legacy_status = legacy_status.replace("Implement ingestion", "M1 complete with docs/ingestion-check.txt; M2 conversion is in progress")
        legacy_status = legacy_status.replace("## 阻塞\n- 无", "## 阻塞\n- M2 awaits the owner's conversion fixture")
        self.assertIn("M2 awaits the owner's conversion fixture", legacy_status)
        legacy_status_path.write_text(legacy_status, encoding="utf-8")
        old_plan_bytes = (self.workspace / "research/PLAN.md").read_bytes()
        old_status_bytes = legacy_status_path.read_bytes()
        state_path = self.input_json(migrated_state)
        tracking_authorization = "User authorized key-event tracking for the reviewed migration only."
        tracking_coordinator = "Migration coordinator"
        tracking_arguments = ["--authorization", tracking_authorization, "--coordinator", tracking_coordinator]
        expected_state = copy.deepcopy(migrated_state)
        expected_state["authorization"] += [tracking_authorization, "Coordinator: " + tracking_coordinator]
        hashes = {
            "hashes": {
                "plan": hashlib.sha256((self.workspace / "research/PLAN.md").read_bytes()).hexdigest(),
                "status": hashlib.sha256((self.workspace / "research/STATUS.md").read_bytes()).hexdigest(),
            }
        }
        before = self.snapshot()
        self.assert_success(self.run_cli("enable-tracking", "--status-file", state_path, "--claude-bridge", *tracking_arguments))
        self.assertEqual(self.snapshot(), before)
        self.assert_failure(self.run_cli("enable-tracking", "--apply", "--claude-bridge", *self.expected_arguments(hashes)))
        self.assertEqual(self.snapshot(), before)
        self.assert_success(self.run_cli("enable-tracking", "--apply", "--status-file", state_path, "--claude-bridge", *tracking_arguments, *self.expected_arguments(hashes)))
        current = self.resume()
        self.assertEqual(current["status"], expected_state)
        self.assertEqual(current["status"]["current_milestone"], "M2")
        self.assertEqual(current["status"]["milestones"][0]["acceptance"], "accepted")
        self.assertEqual(current["status"]["milestones"][1]["execution"], "running")
        self.assertEqual(current["status"]["blockers"], migrated_state["blockers"])
        backups = {key: value for key, value in self.snapshot().items() if key not in before}
        self.assertIn(old_plan_bytes, backups.values())
        self.assertIn(old_status_bytes, backups.values())
        self.assertIn(agents_bytes, backups.values())
        self.assertIn(claude_bytes, backups.values())
        self.assertIn(agents, (self.workspace / "AGENTS.md").read_text(encoding="utf-8"))
        bridge = (self.workspace / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(claude, bridge)
        self.assertEqual(bridge.count("@AGENTS.md"), 1)
        after = self.snapshot()
        self.assert_success(self.run_cli("enable-tracking", "--apply", "--claude-bridge", *self.expected_arguments(current)))
        self.assertEqual(self.snapshot(), after)
        self.assert_success(self.run_cli("validate"))

    def test_read_only_v2_resume_does_not_implicitly_enable_tracking(self):
        result = subprocess.run(
            [sys.executable, str(LEGACY_INIT), "--workspace-root", str(self.workspace), "--plan-file", str(self.input_json(plan()))],
            capture_output=True, text=True, check=False,
        )
        self.assert_success(result)
        before = self.snapshot()
        self.assert_success(self.run_cli("resume"))
        self.assert_success(self.run_cli("enable-tracking"))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.workspace / "AGENTS.md").exists())

    def test_corrupt_status_is_reported_without_automatic_repair(self):
        self.initialize()
        path = self.workspace / "research/STATUS.md"
        path.write_text("---\nrecord: STATUS\n---\nUnparseable state\n", encoding="utf-8")
        before = self.snapshot()
        for command in ("resume", "validate", "handoff", "enable-tracking"):
            with self.subTest(command=command):
                self.assert_failure(self.run_cli(command))
                self.assertEqual(self.snapshot(), before)

    def test_checkpoint_missing_source_hash_is_rejected_without_repair(self):
        initial = self.initialize()
        self.assert_success(self.checkpoint(self.update(self.progressing_state(initial)), initial))
        records = list((self.workspace / "research/records/checkpoints").glob("*.md"))
        self.assertEqual(len(records), 1)
        original = records[0].read_text(encoding="utf-8")
        corrupted = "\n".join(line for line in original.split("\n") if not line.startswith("source_status_hash:"))
        self.assertNotEqual(corrupted, original)
        records[0].write_text(corrupted, encoding="utf-8")
        before = self.snapshot()
        for command in ("resume", "validate"):
            with self.subTest(command=command):
                self.assert_failure(self.run_cli(command))
                self.assertEqual(self.snapshot(), before)

    def test_handoff_contains_selected_approach_success_and_milestone_acceptance(self):
        self.initialize()
        before = self.snapshot()
        result = self.run_cli("handoff")
        self.assert_success(result)
        frozen = plan()
        for expected in [frozen["selected_approach"], *frozen["success_criteria"], *[item for milestone in frozen["milestones"] for item in milestone["acceptance"]]]:
            with self.subTest(expected=expected):
                self.assertIn(expected, result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_checkpoint_schema_and_unknown_milestone_do_not_write(self):
        initial = self.initialize()
        variants = []
        unknown_key = self.update(initial["status"], "unknown-key")
        unknown_key["unexpected"] = True
        variants.append(unknown_key)
        unknown_milestone = self.update(initial["status"], "unknown-milestone")
        unknown_milestone["status"]["current_milestone"] = "M99"
        variants.append(unknown_milestone)
        invalid_date = self.update(initial["status"], "invalid-date")
        invalid_date["date"] = "2026-5-12"
        variants.append(invalid_date)
        for update in variants:
            with self.subTest(identifier=update["id"]):
                before = self.snapshot()
                self.assert_failure(self.checkpoint(update, initial))
                self.assertEqual(self.snapshot(), before)

    def test_handoff_output_cannot_escape_the_workspace(self):
        self.initialize()
        before = self.snapshot()
        escaped = self.base / "escaped-handoff.md"
        result = self.run_cli("handoff", "--output", "../escaped-handoff.md")
        self.assert_failure(result)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(escaped.exists())


if __name__ == "__main__":
    unittest.main()
