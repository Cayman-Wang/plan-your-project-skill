"""Host-neutral contracts for handoff, clarification backfill and routing.

These checks are static: they prove the shipped files and the validator agree.
They do not measure live model routing or model instruction following.
"""

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "handoff_check.py"
TEMPLATE = ROOT / "assets" / "TEMPLATE_handoff.md"

REQUIRED_FIELDS = ("goal", "non_goals", "files_and_interfaces", "constraints", "acceptance", "rollback", "open_questions")

COMPLETE_HANDOFF = """# 执行交接：导入器

## 1. 目标
交付可运行的导入器。

## 2. 非目标
无

## 3. 涉及文件与接口
`src/importer.py` 读取旧格式并输出新格式。

## 4. 不可破坏的约束
保持现有解析器的行为与命令行参数。

## 5. 验收命令
```bash
python -m pytest tests/test_importer.py -q
```
预期退出码 0。

## 6. 回退办法
还原 `src/importer.py` 到上一个提交。

## 7. 未决问题
无
"""


def run_checker(*arguments, stdin=None):
    return subprocess.run(
        [sys.executable, "-B", str(CHECKER), *map(str, arguments)],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )


class HandoffTemplateTests(unittest.TestCase):
    def test_template_ships_every_required_section(self):
        self.assertTrue(TEMPLATE.is_file(), "Handoff template must ship with the skill")
        text = TEMPLATE.read_text(encoding="utf-8")
        for field in REQUIRED_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, text.lower().replace("-", "_"))

    def test_entrypoint_links_template_and_checker(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("assets/TEMPLATE_handoff.md", content)
        self.assertIn("scripts/handoff_check.py", content)
        self.assertIn("optional", content.lower())

    def test_template_is_optional_and_does_not_demand_code(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("可选", text)
        self.assertNotIn("必须写入完整实现", text)


class HandoffCheckerTests(unittest.TestCase):
    def test_help_is_available(self):
        result = run_checker("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("handoff", result.stdout.lower())

    def test_complete_handoff_passes(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "交接 文档.md"
            path.write_text(COMPLETE_HANDOFF, encoding="utf-8")
            result = run_checker("--file", path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_section_is_reported(self):
        broken = COMPLETE_HANDOFF.split("## 5. 验收命令")[0] + "## 6. 回退办法\n还原上一个提交。\n\n## 7. 未决问题\n无\n"
        result = run_checker(stdin=broken)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("acceptance", result.stdout.lower() + result.stderr.lower())

    def test_placeholder_only_section_is_rejected(self):
        broken = COMPLETE_HANDOFF.replace("还原 `src/importer.py` 到上一个提交。", "<待填>")
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "handoff.md"
            path.write_text(broken, encoding="utf-8")
            result = run_checker("--file", path, "--json")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("rollback", payload["empty"])

    def test_unreplaced_placeholder_rejects_section(self):
        broken = COMPLETE_HANDOFF.replace("交付可运行的导入器。", "交付 <项目名> 的导入器。")
        result = run_checker("--json", stdin=broken)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("goal", payload["empty"])

    def test_explicit_none_is_accepted(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "handoff.md"
            path.write_text(COMPLETE_HANDOFF, encoding="utf-8")
            result = run_checker("--file", path, "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["valid"])
            self.assertEqual(payload["missing"], [])


class ClarificationBackfillTests(unittest.TestCase):
    def test_discussion_protocol_maps_answers_to_frozen_fields(self):
        text = (ROOT / "references/discussion_protocol_zh.md").read_text(encoding="utf-8")
        for field in ("Outcomes", "Scope", "Constraints", "Milestones and Acceptance", "Risks", "Open Decisions"):
            with self.subTest(field=field):
                self.assertIn(field, text)
        self.assertIn("回写", text)
        self.assertIn("每个已答问题", text)

    def test_host_neutral_behavior_case_exists(self):
        data = json.loads((ROOT / "tests/behavior_evals.json").read_text(encoding="utf-8"))
        ids = [case["id"] for case in data["cases"]]
        self.assertIn("clarification_backfill_maps_answers", ids)
        case = next(c for c in data["cases"] if c["id"] == "clarification_backfill_maps_answers")
        self.assertGreaterEqual(len(case["observable_criteria"]), 4)
        self.assertIn("field", " ".join(case["observable_criteria"]).lower())


class RoutingDescriptionTests(unittest.TestCase):
    def test_description_covers_all_four_intents(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        description = next(line.removeprefix("description: ") for line in content.splitlines() if line.startswith("description: "))
        self.assertEqual(description, "Discuss, plan, resume, or hand off projects.")
        self.assertLessEqual(len(description), 60)

    def test_trigger_cases_cover_positive_and_negative_prompts(self):
        path = ROOT / "tests/trigger_cases.json"
        self.assertTrue(path.is_file(), "Provide real routing inputs separately from measured results")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn(data["status"], {"not_run", "measured"})
        cases = data["cases"]
        self.assertEqual(len(cases), 10)
        positives = [c for c in cases if c["expect_skill"]]
        negatives = [c for c in cases if not c["expect_skill"]]
        self.assertEqual(len(positives), 6)
        self.assertEqual(len(negatives), 4)
        self.assertEqual(len({c["id"] for c in cases}), 10)
        self.assertTrue(any("交接" in c["prompt"] for c in positives), "Cover the handoff phrasing")
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["prompt"].strip())
                if data["status"] == "not_run":
                    self.assertNotIn("result", case)
                    self.assertNotIn("last_result", case)

    def test_measured_routing_evidence_matches_fixture(self):
        """A measured status must ship evidence that agrees with every case and its expectation."""
        path = ROOT / "tests/trigger_cases.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["status"] == "not_run":
            self.skipTest("Routing cases have not been measured yet")
        measured = data["measured"]
        for key in ("date", "host", "model", "provider", "result", "evidence"):
            self.assertTrue(measured.get(key), f"measured fixture needs {key}")
        evidence_path = ROOT / measured["evidence"]
        self.assertTrue(evidence_path.is_file(), "measured status needs a shipped evidence file")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        cases = data["cases"]
        self.assertEqual(evidence["cases_run"], len(cases))
        self.assertEqual(evidence["cases_passed"], sum(1 for r in evidence["cases"] if r["routing_pass"]))
        self.assertEqual(measured["result"], f"{evidence['cases_passed']}/{evidence['cases_run']} matched expectation")
        by_id = {r["id"]: r for r in evidence["cases"]}
        self.assertEqual(set(by_id), {c["id"] for c in cases})
        for case in cases:
            with self.subTest(case=case["id"]):
                record = by_id[case["id"]]
                self.assertEqual(record["expect_skill"], case["expect_skill"])
                self.assertEqual(record["routing_pass"], record["target_loaded"] == case["expect_skill"])
                self.assertEqual(case["last_result"], "pass" if record["routing_pass"] else "fail")
                self.assertEqual(case["last_skills_loaded"], record["skills_loaded"])
                if record["routing_pass"] and case["expect_skill"]:
                    self.assertIn("plan-your-project", record["skills_loaded"])
                if record["routing_pass"] and not case["expect_skill"]:
                    self.assertNotIn("plan-your-project", record["skills_loaded"])
        for rel in ("tests/trigger_cases.json", measured["evidence"]):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("C:/", text, f"{rel} must not embed a local absolute path")
            self.assertNotIn("C:\\\\", text, f"{rel} must not embed a local absolute path")


class CrossHostParityTests(unittest.TestCase):
    def test_shared_sections_avoid_host_specific_tools(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        before, marker, after = content.partition("## Hermes")
        self.assertTrue(marker, "Keep the Hermes section explicit")
        _, _, remainder = after.partition("\n## ")
        shared = before + "\n## " + remainder
        for token in ("skill_view", "clarify", "delegate_task", "/plan"):
            with self.subTest(token=token):
                self.assertNotIn(token, shared)

    def test_codex_adapter_is_preserved(self):
        adapter = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$plan-your-project", adapter)
        self.assertIn("display_name", adapter)

    def test_shipped_files_contain_no_machine_local_paths(self):
        targets = [ROOT / "SKILL.md", ROOT / "README.md", ROOT / "agents/openai.yaml"]
        targets += sorted((ROOT / "references").glob("*.md"))
        targets += sorted((ROOT / "assets").glob("*.md"))
        targets += sorted((ROOT / "scripts").glob("*.py"))
        for path in targets:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("C:/Users/Tangyuan", text)
                self.assertNotIn("C:\\Users\\Tangyuan", text)


if __name__ == "__main__":
    unittest.main()
