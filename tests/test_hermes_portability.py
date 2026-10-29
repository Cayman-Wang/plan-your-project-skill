"""Hermes packaging regressions; stdlib only, no host install or model calls.

The reference-only fixture deliberately models the smaller direct-URL bundle,
not GitHub's full-directory route. It cannot certify model instruction following.
"""

from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUPPORT_LINK = re.compile(
    r"(?:\]\(|`|(?:^|[\s\"']))"
    r"((?:references|templates|scripts|assets|examples)/[^\s)`\"'<>]+)",
    re.MULTILINE,
)


def reference_bundle(destination):
    """Copy only the exact local support references in this skill's entrypoint."""
    destination.mkdir(parents=True)
    content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    shutil.copy2(ROOT / "SKILL.md", destination / "SKILL.md")
    paths = {match.group(1).rstrip(".,;:") for match in SUPPORT_LINK.finditer(content)}
    for relative in sorted(paths):
        source = ROOT / relative
        if not source.is_file():
            raise AssertionError(f"Missing declared support file: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


class HermesReferenceBundleTests(unittest.TestCase):
    def test_reference_only_bundle_contains_complete_license(self):
        with tempfile.TemporaryDirectory() as raw:
            installed = reference_bundle(Path(raw) / "skills" / "计划 skill")
            license_path = installed / "assets/LICENSE"
            self.assertTrue(license_path.is_file(), "Reference-only bundles must include assets/LICENSE")
            self.assertEqual(
                license_path.read_text(encoding="utf-8"),
                (ROOT / "LICENSE").read_text(encoding="utf-8"),
                "Bundled license must preserve the complete root LICENSE text",
            )

    def test_reference_only_bundle_runs_cli_from_an_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            installed = reference_bundle(base / "skills" / "计划 skill")
            workspace = base / "用户项目 with spaces"
            workspace.mkdir()
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
            result = subprocess.run(
                [sys.executable, "-B", str(installed / "scripts/project_state.py"), "--help"],
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("resume", result.stdout)
            self.assertEqual(list(workspace.iterdir()), [])


class HermesDocumentationTests(unittest.TestCase):
    def test_hermes_entrypoint_is_discoverable_and_mode_aware(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        description = next(line.removeprefix("description: ") for line in content.splitlines() if line.startswith("description: "))
        self.assertLessEqual(len(description), 60)
        for trigger in ("discuss", "plan", "resum"):
            self.assertIn(trigger, description.lower())
        self.assertIn("references/hermes_integration_zh.md", content)
        self.assertIn("/plan", content)
        guide_path = ROOT / "references/hermes_integration_zh.md"
        self.assertTrue(guide_path.is_file(), "Hermes integration guide must ship in the bundle")
        guide = guide_path.read_text(encoding="utf-8")
        for contract in ("skill_dir", "--workspace-root", ".hermes/plans/", "research/STATUS.md", "tracking", "clarify", "delegate_task"):
            self.assertIn(contract, guide)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("references/hermes_integration_zh.md", readme)
        self.assertIn("Hermes", readme)
        self.assertTrue((ROOT / "agents/openai.yaml").is_file(), "Keep the existing Codex adapter")


    def test_hermes_behavior_cases_cover_boundaries_without_claiming_model_runs(self):
        path = ROOT / "tests/hermes_behavior_evals.json"
        self.assertTrue(path.is_file(), "Provide separate Hermes behavior inputs, not invented run results")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "not_run")
        cases = data["cases"]
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {
            "hermes_plan_mode_with_tracking",
            "hermes_discuss_without_writes",
            "hermes_save_without_enabling_tracking",
            "hermes_skill_dir_is_not_workspace",
            "hermes_remote_backend_missing_skill",
            "hermes_single_coordinator",
        })
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["prompt"])
                self.assertTrue(case["raw_project_summary"])
                self.assertGreaterEqual(len(case["observable_criteria"]), 3)
                self.assertNotIn("passed", case)
                self.assertNotIn("actual_response", case)


if __name__ == "__main__":
    unittest.main()
