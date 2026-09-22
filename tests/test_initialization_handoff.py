"""Focused regressions for first-session setup and portable handoff structure."""

import contextlib
import io
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

import test_project_state as fixtures

sys.path.insert(0, str(fixtures.ROOT / "scripts"))
import project_state as STATE
import workspace_io as IO


class InitializationHandoffTests(unittest.TestCase):
    # Reuse fixture helpers without inheriting its test cases a second time.
    setUp = fixtures.ProjectStateCLITests.setUp
    input_json = fixtures.ProjectStateCLITests.input_json
    run_cli = fixtures.ProjectStateCLITests.run_cli
    assert_success = fixtures.ProjectStateCLITests.assert_success
    assert_failure = fixtures.ProjectStateCLITests.assert_failure
    snapshot = fixtures.ProjectStateCLITests.snapshot
    resume = fixtures.ProjectStateCLITests.resume

    def init_arguments(self, *arguments):
        return ["--plan-file", str(self.input_json(fixtures.plan())), *arguments]

    def tracking_arguments(self, *arguments):
        return ["--enable-tracking", "--authorization", "Planning records are authorized; implementation is not authorized.", "--coordinator", "Main coordinator", *arguments]

    def substantive_files(self):
        return {path: raw for path, raw in self.snapshot().items() if path != IO.LOCK_NAME}

    def test_default_init_keeps_two_core_files_and_no_entry_or_checkpoint(self):
        self.assert_success(self.run_cli("init", *self.init_arguments()))
        self.assertEqual(set(self.substantive_files()), {"research/PLAN.md", "research/STATUS.md"})
        current = self.resume()
        self.assertEqual(current["plan_revision"], 1)
        self.assertEqual(current["status_revision"], 1)

    def test_one_init_records_exact_authorization_coordinator_and_entry_rules(self):
        authorization = [
            "User authorized planning and project records only; implementation is not authorized.",
            "Network access and publication require a separate user instruction.",
        ]
        args = self.init_arguments("--with-agents", "--claude-bridge", "--enable-tracking", "--coordinator", "Main coordinator")
        for instruction in authorization:
            args += ["--authorization", instruction]
        self.assert_success(self.run_cli("init", *args))
        current = self.resume()
        self.assertEqual(current["status"]["authorization"], authorization + ["Coordinator: Main coordinator"])
        self.assertEqual(current["plan_revision"], 1)
        self.assertEqual(current["status_revision"], 1)
        self.assertTrue(all(row["execution"] == "pending" for row in current["status"]["milestones"]))
        self.assertEqual(set(self.substantive_files()), {"research/PLAN.md", "research/STATUS.md", "AGENTS.md", "CLAUDE.md"})
        agents = (self.workspace / "AGENTS.md").read_text()
        self.assertEqual(agents.count(STATE.START), 1)
        self.assertEqual(agents.count(STATE.END), 1)
        self.assertIn("research/STATUS.md", agents)
        self.assertIn("research/PLAN.md", agents)
        self.assertEqual((self.workspace / "CLAUDE.md").read_text().splitlines().count("@AGENTS.md"), 1)

    def test_init_merges_existing_rules_and_preserves_exact_original_bytes(self):
        originals = {
            "AGENTS.md": b"# Existing project rules\r\n\r\nPreserve review ownership.\r\n",
            "CLAUDE.md": b"# Existing Claude rules\r\n\r\nPreserve local commands.\r\n",
        }
        for name, content in originals.items():
            (self.workspace / name).write_bytes(content)
        self.assert_success(self.run_cli("init", *self.init_arguments(*self.tracking_arguments("--with-agents", "--claude-bridge"))))
        backups = {
            path.name: path.read_bytes()
            for path in (self.workspace / ".plan-your-project-backups").rglob("*")
            if path.is_file()
        }
        self.assertEqual(backups, originals)
        for name, content in originals.items():
            self.assertTrue((self.workspace / name).read_bytes().startswith(content.rstrip()))
        self.assertEqual((self.workspace / "CLAUDE.md").read_text().splitlines().count("@AGENTS.md"), 1)
        self.assertEqual(self.resume()["status_revision"], 1)

    def test_init_does_not_back_up_unchanged_bridge_or_new_core_files(self):
        bridge = b"# Existing rules\r\n@AGENTS.md\r\n"
        (self.workspace / "CLAUDE.md").write_bytes(bridge)
        self.assert_success(self.run_cli("init", *self.init_arguments(*self.tracking_arguments("--with-agents", "--claude-bridge"))))
        self.assertEqual((self.workspace / "CLAUDE.md").read_bytes(), bridge)
        self.assertEqual(set(self.substantive_files()), {"research/PLAN.md", "research/STATUS.md", "AGENTS.md", "CLAUDE.md"})

    def test_init_dry_run_previews_all_core_and_entry_changes_without_writing(self):
        (self.workspace / "AGENTS.md").write_bytes(b"# Existing project rules\r\n")
        (self.workspace / "CLAUDE.md").write_bytes(b"# Existing Claude rules\r\n")
        before = self.snapshot()
        result = self.run_cli("init", *self.init_arguments(
            "--with-agents", "--claude-bridge", "--enable-tracking", "--authorization", "Planning only; no implementation.",
            "--coordinator", "Main coordinator", "--dry-run",
        ))
        self.assert_success(result)
        preview = json.loads(result.stdout)
        self.assertEqual(preview["result"], "preview")
        expected = {"research/PLAN.md", "research/STATUS.md", "AGENTS.md", "CLAUDE.md"}
        diffs = {Path(name).as_posix(): value for name, value in preview["diffs"].items()}
        self.assertTrue(expected <= set(diffs))
        for name in expected:
            self.assertIn("+++ ", diffs[name])
            self.assertIn("@@", diffs[name])
        self.assertIn("Planning only; no implementation.", diffs["research/STATUS.md"])
        self.assertIn("Coordinator: Main coordinator", diffs["research/STATUS.md"])
        self.assertEqual(self.snapshot(), before)

    def test_init_validation_failure_rolls_back_core_entries_and_backups_together(self):
        originals = {"AGENTS.md": b"Existing project rules\r\n", "CLAUDE.md": b"Existing Claude rules\r\n"}
        for name, content in originals.items():
            (self.workspace / name).write_bytes(content)
        args = ["init", "--workspace-root", str(self.workspace), "--json", *self.init_arguments(*self.tracking_arguments("--with-agents", "--claude-bridge"))]
        validation_saw_complete_write = []
        original_read = STATE.read_workspace
        def reject_written_state(root, *args, **kwargs):
            if kwargs.get("allow_pending"):
                self.assertTrue((root / "research/PLAN.md").is_file())
                self.assertTrue((root / "research/STATUS.md").is_file())
                self.assertIn(STATE.START, (root / "AGENTS.md").read_text())
                self.assertIn("@AGENTS.md", (root / "CLAUDE.md").read_text())
                validation_saw_complete_write.append(True)
                raise STATE.Error("Injected validation rejection")
            return original_read(root, *args, **kwargs)
        with mock.patch.object(STATE, "read_workspace", side_effect=reject_written_state):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = STATE.main(args)
        self.assertEqual(result, 1)
        self.assertEqual(validation_saw_complete_write, [True])
        self.assertEqual(self.substantive_files(), originals)
        self.assertFalse(IO.pending_transaction(self.workspace))

    def test_init_rejects_symlink_entries_without_touching_destinations(self):
        for name in ("AGENTS.md", "CLAUDE.md"):
            with self.subTest(entry=name):
                root = self.base / name.removesuffix(".md")
                root.mkdir()
                outside = self.base / (name + ".outside")
                original = b"Preserve external rules\r\n"
                outside.write_bytes(original)
                try:
                    (root / name).symlink_to(outside)
                except OSError as exc:
                    if getattr(exc, "winerror", None) == 1314:
                        self.skipTest(f"symbolic-link safety test requires symlink permission: {exc}")
                    raise
                result = self.run_cli("init", *self.init_arguments(*self.tracking_arguments("--with-agents", "--claude-bridge")), workspace=root)
                self.assert_failure(result)
                self.assertEqual(json.loads(result.stderr)["result"], "error")
                self.assertIn("symbolic link", json.loads(result.stderr)["message"])
                self.assertEqual(outside.read_bytes(), original)
                self.assertTrue((root / name).is_symlink())
                self.assertFalse((root / "research/PLAN.md").exists())
                self.assertFalse((root / "research/STATUS.md").exists())
                self.assertFalse(IO.pending_transaction(root))

    def test_claude_bridge_requires_shared_agents_rules(self):
        result = self.run_cli("init", *self.init_arguments("--claude-bridge"))
        self.assert_failure(result)
        error = json.loads(result.stderr)
        self.assertEqual(error["result"], "error")
        self.assertIn("--with-agents", error["message"])
        self.assertEqual(self.substantive_files(), {})

    def test_handoff_has_one_title_nested_scope_and_status_without_writes(self):
        for language, scope, children in (("en", "Scope", ("In", "Out")), ("zh", "范围", ("范围内", "范围外"))):
            with self.subTest(language=language):
                root = self.base / language
                root.mkdir()
                self.assert_success(self.run_cli("init", *self.init_arguments("--language", language), workspace=root))
                before = self.snapshot(root)
                result = self.run_cli("handoff", workspace=root)
                self.assert_success(result)
                self.assertIn(str(root.resolve()), result.stdout)
                headings = re.findall(r"(?m)^(#{1,6}) (.+)$", result.stdout)
                self.assertEqual(sum(level == "#" for level, title in headings), 1)
                self.assertIn(("###", scope), headings)
                for child in children:
                    self.assertIn(("####", child), headings)
                self.assertIn(("###", "Summary"), headings)
                self.assertIn(("###", "Milestones"), headings)
                self.assertIn(("####", "M1"), headings)
                self.assertNotIn(("##", "Summary"), headings)
                self.assertNotIn(("###", "M1"), headings)
                self.assertEqual(self.snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
