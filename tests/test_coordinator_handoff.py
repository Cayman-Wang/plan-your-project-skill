"""Focused coordinator-ownership lifecycle regressions for project_state."""

import copy
import json
import unittest

import test_project_state as fixtures


class CoordinatorHandoffTests(unittest.TestCase):
    # Reuse the small synthetic workspace fixture without inheriting its suite.
    for _name in (
        "setUp", "input_json", "run_cli", "assert_success", "assert_failure", "snapshot",
        "resume", "initialize", "expected_arguments", "update", "checkpoint",
        "progressing_state", "evidence", "accepted_milestone",
    ):
        locals()[_name] = getattr(fixtures.ProjectStateCLITests, _name)
    del _name

    def init_tracking(self, owner="Alice", authorization="Original tracking agreement"):
        self.assert_success(self.run_cli(
            "init", "--plan-file", self.input_json(fixtures.plan()), "--enable-tracking",
            "--authorization", authorization, "--coordinator", owner,
        ))
        return self.resume()

    def enable(self, resumed, owner, authorization):
        return self.run_cli(
            "enable-tracking", "--apply", "--authorization", authorization,
            "--coordinator", owner, *self.expected_arguments(resumed),
        )

    @staticmethod
    def coordinators(state):
        return [line.removeprefix("Coordinator: ") for line in state["authorization"]
                if line.startswith("Coordinator:")]

    def test_handoff_replaces_owner_preserves_progress_and_records_reason(self):
        before = self.init_tracking()
        progressed = self.progressing_state(before)
        progressed["authorization"] = copy.deepcopy(before["status"]["authorization"])
        self.assert_success(self.checkpoint(self.update(progressed, "m1-accepted-m2-running"), before))
        before = self.resume()
        plan_bytes = (self.workspace / "research/PLAN.md").read_bytes()
        milestones = copy.deepcopy(before["status"]["milestones"])
        evidence = copy.deepcopy(before["status"]["evidence"])
        files_before = self.snapshot()
        reason = "User approved Alice-to-Bob handoff after the ownership change."

        self.assert_success(self.enable(before, "Bob", reason))
        after = self.resume()

        self.assertEqual(self.coordinators(after["status"]), ["Bob"])
        self.assertIn("Original tracking agreement", after["status"]["authorization"])
        self.assertEqual(after["status"]["milestones"], milestones)
        self.assertEqual(after["status"]["evidence"], evidence)
        self.assertEqual(after["status"]["milestones"][0]["acceptance"], "accepted")
        self.assertEqual(after["status"]["milestones"][1]["execution"], "running")
        self.assertEqual((self.workspace / "research/PLAN.md").read_bytes(), plan_bytes)
        files_after = self.snapshot()
        records = [path for path in files_after if path.startswith("research/records/checkpoints/")
                   and path not in files_before]
        self.assertEqual(len(records), 1)
        record = files_after[records[0]].decode("utf-8")
        for text in ("Alice", "Bob", reason, before["hashes"]["status"], before["hashes"]["plan"]):
            self.assertIn(text, record)
        self.assertTrue((self.workspace / ".plan-your-project-backups").is_dir())
        self.assert_success(self.run_cli("validate"))

    def test_repeating_same_owner_and_agreement_is_idempotent(self):
        initial = self.init_tracking("Bob", "Tracking is owned by Bob.")
        # The first call can install the managed entry; the identical replay cannot write again.
        self.assert_success(self.enable(initial, "Bob", "Tracking is owned by Bob."))
        current = self.resume()
        before = self.snapshot()

        result = self.enable(current, "Bob", "Tracking is owned by Bob.")

        self.assert_success(result)
        self.assertEqual(json.loads(result.stdout)["result"], "unchanged")
        self.assertEqual(self.snapshot(), before)

    def test_compatibility_state_without_owner_can_set_one(self):
        initial = self.initialize()
        state = copy.deepcopy(initial["status"])
        state["summary"] = "A prior disabled workspace records the authorization but no coordinator."
        state["authorization"] = ["Existing tracking authorization without a coordinator."]
        self.assert_success(self.checkpoint(self.update(state, "compatibility-authority"), initial))
        current = self.resume()

        self.assert_success(self.enable(current, "Alice", "User selected the first shared-status owner."))
        after = self.resume()["status"]

        self.assertEqual(self.coordinators(after), ["Alice"])
        self.assertIn("Existing tracking authorization without a coordinator.", after["authorization"])
        self.assert_success(self.run_cli("validate"))

    def test_ambiguous_legacy_owners_warn_read_only_and_explicit_handoff_repairs(self):
        initial = self.init_tracking()
        status_path = self.workspace / "research/STATUS.md"
        status_path.write_text(
            status_path.read_text(encoding="utf-8").replace(
                "- Coordinator: Alice\n", "- Coordinator: Alice\n- Coordinator: Bob\n",
            ), encoding="utf-8",
        )

        before = self.snapshot()
        resumed = self.resume()
        self.assertTrue(any("coordinator" in warning.lower() and
                            ("multiple" in warning.lower() or "ambiguous" in warning.lower())
                            for warning in resumed["warnings"]))
        self.assertEqual(self.snapshot(), before)
        handoff = self.run_cli("handoff")
        self.assert_success(handoff)
        self.assertIn("Coordinator", handoff.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assert_failure(self.run_cli("validate"))
        self.assertEqual(self.snapshot(), before)
        self.assert_failure(self.run_cli("enable-tracking", "--apply", *self.expected_arguments(resumed)))
        self.assertEqual(self.snapshot(), before)

        self.assert_success(self.enable(resumed, "Bob", "User confirmed Bob takes over the ambiguous legacy state."))
        repaired = self.resume()["status"]
        self.assertEqual(self.coordinators(repaired), ["Bob"])
        self.assert_success(self.run_cli("validate"))

    def test_authorization_cannot_inject_coordinator_or_checkpoint_duplicates(self):
        self.assert_failure(self.run_cli(
            "init", "--plan-file", self.input_json(fixtures.plan()), "--enable-tracking",
            "--authorization", "Coordinator: injected owner", "--coordinator", "Alice",
        ))
        self.assertFalse((self.workspace / "research/PLAN.md").exists())
        self.assertFalse((self.workspace / "research/STATUS.md").exists())

        current = self.init_tracking()
        for identifier, coordinator in (("competing-owner", "Coordinator: Bob"),
                                        ("empty-owner", "Coordinator:")):
            with self.subTest(coordinator=coordinator):
                state = copy.deepcopy(current["status"])
                state["summary"] = "A malformed update attempts to add an invalid owner."
                state["authorization"].append(coordinator)
                before = self.snapshot()
                self.assert_failure(self.checkpoint(self.update(state, identifier), current))
                self.assertEqual(self.snapshot(), before)

    def test_explicit_owner_only_checkpoint_preserves_disabled_mode_and_progress(self):
        self.assert_success(self.run_cli(
            "init", "--plan-file", self.input_json(fixtures.plan()),
            "--authorization", "User authorized import implementation and explicitly requested records only.",
            "--coordinator", "Alice",
        ))
        initial = self.resume()
        progressed = self.progressing_state(initial)
        progressed["authorization"] = copy.deepcopy(initial["status"]["authorization"])
        progressed["state"] = "blocked"
        progressed["blockers"] = ["M2 awaits the conversion fixture"]
        self.assert_success(self.checkpoint(self.update(progressed, "explicit-progress-note"), initial))
        current = self.resume()
        self.assertEqual(current["tracking"], "disabled")

        reason = "User requested only Alice-to-Bob handoff; automatic recording remains disabled."
        state = copy.deepcopy(current["status"])
        state["authorization"] = [item for item in state["authorization"]
                                  if not item.lstrip().startswith("Coordinator:")]
        state["authorization"] += [reason, "Coordinator: Bob"]
        request = self.update(state, "owner-only-handoff", "Save the requested ownership change")
        request["changes"] = ["Coordinator changed: Alice -> Bob", reason]
        before = self.snapshot()

        self.assert_failure(self.checkpoint(request, initial))
        self.assertEqual(self.snapshot(), before)
        self.assert_success(self.checkpoint(request, current))
        after = self.resume()
        self.assertEqual(after["tracking"], "disabled")
        self.assertEqual(after["status"], state)
        self.assertEqual(after["hashes"]["plan"], current["hashes"]["plan"])
        self.assertEqual(after["status_revision"], current["status_revision"] + 1)
        files_after = self.snapshot()
        added = set(files_after) - set(before)
        self.assertEqual(len(added), 1)
        record_path = added.pop()
        self.assertTrue(record_path.startswith("research/records/checkpoints/"))
        record = files_after[record_path].decode("utf-8")
        for value in ("Alice", "Bob", reason, current["hashes"]["plan"], current["hashes"]["status"]):
            self.assertIn(value, record)
        for name in before:
            if name != "research/STATUS.md":
                self.assertEqual(files_after[name], before[name])
        for path in ("AGENTS.md", "CLAUDE.md", ".plan-your-project-backups"):
            self.assertFalse((self.workspace / path).exists())
        self.assert_success(self.run_cli("validate"))
        self.assert_success(self.checkpoint(request, current))
        self.assertEqual(self.snapshot(), files_after)

    def test_explicit_checkpoint_repairs_ambiguous_disabled_owners_without_activation(self):
        self.assert_success(self.run_cli(
            "init", "--plan-file", self.input_json(fixtures.plan()), "--coordinator", "Alice",
        ))
        status_path = self.workspace / "research/STATUS.md"
        status_path.write_text(status_path.read_text(encoding="utf-8").replace(
            "- Coordinator: Alice\n", "- Coordinator: Alice\n- Coordinator: Bob\n",
        ), encoding="utf-8")
        current = self.resume()
        self.assertEqual(current["tracking"], "disabled")
        self.assertTrue(any("Ambiguous coordinator" in warning for warning in current["warnings"]))
        self.assert_failure(self.run_cli("validate"))

        state = copy.deepcopy(current["status"])
        state["authorization"] = [item for item in state["authorization"]
                                  if not item.lstrip().startswith("Coordinator:")]
        reason = "User confirmed Carol replaces both old owner entries; recording remains disabled."
        state["authorization"] += [reason, "Coordinator: Carol"]
        request = self.update(state, "resolve-disabled-owners", "Record the confirmed current owner")
        request["changes"] = ["Coordinator changed: Alice, Bob -> Carol", reason]
        self.assert_success(self.checkpoint(request, current))
        after = self.resume()
        self.assertEqual(after["tracking"], "disabled")
        self.assertEqual(after["status"], state)
        self.assertEqual(after["hashes"]["plan"], current["hashes"]["plan"])
        self.assertEqual(self.coordinators(after["status"]), ["Carol"])
        self.assert_success(self.run_cli("validate"))
        records = list((self.workspace / "research/records/checkpoints").glob("*.md"))
        self.assertEqual(len(records), 1)
        history = records[0].read_text(encoding="utf-8")
        for value in ("Alice", "Bob", "Carol", reason):
            self.assertIn(value, history)


if __name__ == "__main__":
    unittest.main()
