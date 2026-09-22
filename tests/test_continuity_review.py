"""Regression coverage for exported context, plan history and tracking consent."""
import copy
import json
import unittest

import test_project_state as fixtures


class ContinuityReviewTests(unittest.TestCase):
    setUp = fixtures.ProjectStateCLITests.setUp
    input_json = fixtures.ProjectStateCLITests.input_json
    run_cli = fixtures.ProjectStateCLITests.run_cli
    assert_success = fixtures.ProjectStateCLITests.assert_success
    assert_failure = fixtures.ProjectStateCLITests.assert_failure
    snapshot = fixtures.ProjectStateCLITests.snapshot
    resume = fixtures.ProjectStateCLITests.resume
    initialize = fixtures.ProjectStateCLITests.initialize
    expected_arguments = fixtures.ProjectStateCLITests.expected_arguments
    update = fixtures.ProjectStateCLITests.update
    checkpoint = fixtures.ProjectStateCLITests.checkpoint
    evidence = fixtures.ProjectStateCLITests.evidence
    accepted_milestone = fixtures.ProjectStateCLITests.accepted_milestone

    def agreement(self):
        return ["--authorization", "User authorized key-event recording for this import project; no implementation or publication.",
                "--coordinator", "Import project main agent"]

    def refreeze(self, resumed, plan, identifier="storage-change"):
        return self.run_cli("refreeze", "--plan-file", self.input_json(plan),
                            "--id", identifier, "--summary", "User approved the revised M3 decision and record.",
                            "--affected-milestone", "M3", *self.expected_arguments(resumed))

    def test_conditional_handoff_carries_decision_context_in_both_languages(self):
        conditional = fixtures.plan(
            freeze_readiness="READY_WITH_ASSUMPTIONS",
            assumptions=["Representative input is assumed to fit in memory; not yet verified."],
            risks=[{"risk": "Production volume may exceed memory.", "mitigation_or_validation": "Measure peak memory before rollout."}],
            open_questions=["Does production input have the same size distribution?"],
        )
        for language in ("zh", "en"):
            with self.subTest(language=language):
                root = self.base / language
                root.mkdir()
                self.assert_success(self.run_cli("init", "--plan-file", self.input_json(conditional), "--language", language, workspace=root))
                before = self.snapshot(root)
                result = self.run_cli("handoff", workspace=root)
                self.assert_success(result)
                for value in [*conditional["assumptions"], *conditional["open_questions"],
                              *conditional["risks"][0].values(), conditional["freeze_readiness"]]:
                    self.assertIn(value, result.stdout)
                self.assertEqual(self.snapshot(root), before)

    def test_refreeze_preserves_changed_decisions_and_old_acceptance_without_git(self):
        initial = self.initialize()
        original = fixtures.plan()
        revised = copy.deepcopy(original)
        revised["locked_decisions"][1] = "Use a chunked store"
        revised["selected_approach"] = "Existing parser with a chunked store"
        revised["alternatives_considered"] = [{"option": "Single-file store", "tradeoffs": ["Unbounded reads"]}]
        revised["milestones"][2]["acceptance"] = ["Chunked storage supports bounded reads"]
        self.assert_success(self.refreeze(initial, revised))
        records = list((self.workspace / "research/records/checkpoints").glob("*.md"))
        self.assertEqual(len(records), 1)
        history = records[0].read_text(encoding="utf-8")
        for value in [original["locked_decisions"][1], revised["locked_decisions"][1],
                      original["milestones"][2]["acceptance"][0], revised["milestones"][2]["acceptance"][0]]:
            self.assertIn(value, history)
        self.assertIn("before, PLAN revision 1", history)
        self.assertIn("after, PLAN revision 2", history)
        self.assertFalse((self.workspace / ".git").exists())
        self.assertFalse((self.workspace / ".plan-your-project-transaction").exists())
        self.assert_success(self.run_cli("validate"))
        before = self.snapshot()
        self.assert_success(self.refreeze(initial, revised))
        self.assertEqual(self.snapshot(), before)

    def test_plain_init_and_explicit_checkpoint_do_not_enable_tracking(self):
        initial = self.initialize()
        self.assertEqual(initial["tracking"], "disabled")
        self.assertFalse((self.workspace / "AGENTS.md").exists())
        state = copy.deepcopy(initial["status"])
        state["summary"] = "User explicitly requested a status note; implementation has not started."
        self.assert_success(self.checkpoint(self.update(state), initial))
        self.assertEqual(self.resume()["tracking"], "disabled")
        self.assertIn("disabled", self.run_cli("handoff").stdout)
        self.assert_success(self.refreeze(self.resume(), fixtures.plan(next_action="Review the revised storage proposal")))
        self.assertEqual(self.resume()["tracking"], "disabled")

    def test_new_tracking_requires_and_records_the_agreement_once(self):
        plan_file = self.input_json(fixtures.plan())
        for extra in (("--enable-tracking",), ("--with-agents",),
                      ("--enable-tracking", "--authorization", "User agreed to tracking")):
            with self.subTest(extra=extra):
                self.assert_failure(self.run_cli("init", "--plan-file", plan_file, *extra))
                self.assertFalse((self.workspace / "research/PLAN.md").exists())
        self.assert_success(self.run_cli("init", "--plan-file", plan_file, "--enable-tracking", "--with-agents", *self.agreement()))
        current = self.resume()
        self.assertEqual(current["tracking"], "key_events")
        self.assertEqual(current["status"]["authorization"], [self.agreement()[1], "Coordinator: " + self.agreement()[3]])
        self.assertEqual(current["status_revision"], 1)
        self.assertFalse((self.workspace / "research/records").exists())
        state = copy.deepcopy(current["status"])
        state["summary"] = "Authorized planning review completed."
        self.assert_success(self.checkpoint(self.update(state), current))
        self.assertEqual(self.resume()["tracking"], "key_events")
        self.assert_success(self.refreeze(self.resume(), fixtures.plan(next_action="Read the updated review")))
        self.assertEqual(self.resume()["tracking"], "key_events")

    def test_enable_tracking_preview_apply_conflict_and_idempotence(self):
        initial = self.initialize()
        before = self.snapshot()
        preview = self.run_cli("enable-tracking")
        self.assert_success(preview)
        self.assertTrue(json.loads(preview.stdout)["requires_tracking_agreement"])
        self.assertEqual(self.snapshot(), before)
        self.assert_failure(self.run_cli("enable-tracking", "--apply", *self.expected_arguments(initial)))
        self.assertEqual(self.snapshot(), before)
        preview = self.run_cli("enable-tracking", *self.agreement())
        self.assert_success(preview)
        diffs = json.loads(preview.stdout)["diffs"]
        status_diff = next(value for key, value in diffs.items() if key.replace("\\", "/") == "research/STATUS.md")
        self.assertIn("+tracking: key_events", status_diff)
        self.assertIn(self.agreement()[1], status_diff)
        self.assertEqual(self.snapshot(), before)
        state = copy.deepcopy(initial["status"])
        state["next_action"] = "Read the newer owner instruction"
        self.assert_success(self.checkpoint(self.update(state), initial))
        newer = self.resume()
        before_apply = self.snapshot()
        self.assert_failure(self.run_cli("enable-tracking", "--apply", *self.agreement(), *self.expected_arguments(initial)))
        self.assertEqual(self.snapshot(), before_apply)
        self.assert_success(self.run_cli("enable-tracking", "--apply", *self.agreement(), *self.expected_arguments(newer)))
        current = self.resume()
        self.assertEqual(current["tracking"], "key_events")
        self.assertEqual(current["status_revision"], newer["status_revision"] + 1)
        self.assertEqual(current["hashes"]["plan"], initial["hashes"]["plan"])
        expected_state = copy.deepcopy(state)
        expected_state["authorization"] += [self.agreement()[1], "Coordinator: " + self.agreement()[3]]
        self.assertEqual(current["status"], expected_state)
        before_repeat = self.snapshot()
        self.assert_success(self.run_cli("enable-tracking", "--apply", *self.agreement(), *self.expected_arguments(current)))
        self.assertEqual(self.snapshot(), before_repeat)

    def test_existing_key_events_workspace_needs_no_new_agreement(self):
        initial = self.initialize()
        status = self.workspace / "research/STATUS.md"
        status.write_text(status.read_text(encoding="utf-8").replace("tracking: disabled", "tracking: key_events"), encoding="utf-8")
        current = self.resume()
        self.assertEqual(current["tracking"], "key_events")
        self.assert_success(self.run_cli("enable-tracking", "--apply", *self.expected_arguments(current)))
        self.assertEqual(self.resume()["status"], initial["status"])

    def test_assessed_negative_or_inconclusive_results_require_evidence(self):
        initial = self.initialize()
        for conclusion in ("not_supported", "inconclusive"):
            with self.subTest(conclusion=conclusion):
                state = copy.deepcopy(initial["status"])
                state["milestones"][0]["conclusion"] = conclusion
                result = self.checkpoint(self.update(state, conclusion.replace("_", "-")), initial)
                self.assert_failure(result)
                self.assertIn("requires observed or historical evidence", result.stderr)
        self.assertEqual(self.resume()["hashes"], initial["hashes"])

    def test_negative_result_can_complete_an_experiment_without_claiming_support(self):
        research = fixtures.plan(milestones=[{"id": "M1", "outcome": "Evaluate the stated hypothesis", "acceptance": ["Run the fixed protocol and report positive, negative or inconclusive results with evidence"]}])
        self.assert_success(self.run_cli("init", "--plan-file", self.input_json(research)))
        current = self.resume()
        for index, conclusion in enumerate(("not_supported", "inconclusive")):
            with self.subTest(conclusion=conclusion):
                state = copy.deepcopy(current["status"])
                item = self.evidence()
                item["summary"] = "Synthetic fixture: the fixed-protocol report records " + conclusion
                (self.workspace / item["ref"]).write_text(item["summary"], encoding="utf-8")
                state["evidence"] = [item]
                self.accepted_milestone(state["milestones"][0], item["id"])
                state["milestones"][0]["conclusion"] = conclusion
                state["milestones"][0]["summary"] = item["summary"]
                state["state"] = "complete"
                self.assert_success(self.checkpoint(self.update(state, f"research-result-{index}"), current))
                self.assertIn(conclusion, self.run_cli("handoff").stdout)
                current = self.resume()
                self.assertEqual(current["status"]["milestones"][0]["conclusion"], conclusion)
                self.assert_success(self.run_cli("validate"))


if __name__ == "__main__":
    unittest.main()
