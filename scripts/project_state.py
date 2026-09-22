#!/usr/bin/env python3
"""Portable, evidence-aware project state. Python standard library only."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import init_research_workspace as legacy
import workspace_io as io

FORMAT = "plan-your-project/v2.1"
HEADINGS = ("Summary", "Milestones", "Running Tasks", "Blockers", "Next Action", "Must Read", "Evidence", "Authorization")
STATE_KEYS = {"summary", "state", "current_milestone", "milestones", "running_tasks", "blockers", "next_action", "must_read", "evidence", "authorization"}
MILESTONE_KEYS = ("id", "execution", "validation", "acceptance", "summary", "evidence", "acceptance_basis", "conclusion")
TASK_KEYS = ("id", "environment", "code_ref", "document_ref", "log", "artifacts", "last_checked_at", "completion", "recovery")
EVIDENCE_KEYS = ("id", "source", "ref", "summary", "code_ref", "checked_at")
SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
IDENTIFIER = r"[A-Za-z0-9][A-Za-z0-9._-]*"
START = "<!-- plan-your-project:tracking:start -->"
END = "<!-- plan-your-project:tracking:end -->"
Error = legacy.ContractError


def require(test, message):
    if not test:
        raise Error(message)


def text(value, name, empty=False):
    legacy.valid_text(value, name)
    require("\x00" not in value and (empty or bool(value.strip())), f"{name} must be nonempty single-line text")


def strings(value, name, required=False):
    legacy.string_list(value, name, required)
    for item in value:
        text(item, name)


def exact(value, keys, name):
    legacy.exact_object(value, keys, name)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    raw = sys.stdin.buffer.read().decode("utf-8-sig") if path == "-" else Path(path).read_text(encoding="utf-8-sig")
    return json.loads(raw, object_pairs_hook=unique)


def paths(root):
    return root / "research/PLAN.md", root / "research/STATUS.md"


def safe_relative(root, value, exists=True):
    text(value, "relative path")
    require(not Path(value).is_absolute() and "\\" not in value and ":" not in value and all(x not in ("", ".", "..") for x in value.split("/")), f"invalid workspace-relative path: {value}")
    result = io.ensure_within(root, root / value)
    require(not exists or result.is_file(), f"missing referenced file: {value}")
    return result


def sections(body, headings):
    require(re.findall(r"(?m)^## (.+)$", body) == list(headings), "missing, duplicated or reordered sections")
    return {h: legacy.section_body(body, h) for h in headings}


def parse_list(raw):
    if raw == "- (none)":
        return []
    rows = raw.splitlines()
    require(all(x.startswith("- ") and len(x) > 2 for x in rows), "invalid list section")
    return [x[2:] for x in rows]


def render_records(records, keys):
    if not records:
        return "- (none)"
    out = []
    for record in records:
        out.append("### " + record["id"])
        for key in keys:
            if key == "id":
                continue
            value = record[key]
            if key == "evidence":
                value = ",".join(value)
            out.append(f"- {key}: {value}")
    return "\n".join(out)


def parse_records(raw, keys):
    if raw == "- (none)":
        return []
    records = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("### "):
            records.append({"id": line[4:]})
        else:
            require(records and line.startswith("- ") and ":" in line, "invalid record line")
            key, value = line[2:].split(":", 1)
            require(key in keys and key != "id" and key not in records[-1], "duplicate or unknown record field")
            value = value.removeprefix(" ")
            records[-1][key] = [item.strip() for item in value.split(",")] if key == "evidence" and value else [] if key == "evidence" else value
    for record in records:
        exact(record, keys, "record")
    return records


def read_plan(plan_text):
    pm, body = legacy.metadata(plan_text)
    require(pm.get("workspace_format") in (FORMAT, "plan-your-project/v2"), "unsupported PLAN format")
    language = pm.get("language", "zh")
    mh = "里程碑" if language == "zh" else "Milestones"
    entries = {}
    for line in (legacy.section_body(body, mh) or "").splitlines():
        if line.startswith("- ") and " - " in line:
            key = line[2:].split(" - ", 1)[0]
            require(key not in entries, "duplicate milestone ID in PLAN")
            entries[key] = line
    require(entries, "PLAN has no milestones")
    # Reuse the same readiness/scope/acceptance validation as legacy input/output.
    stub = {"milestones": [{"id": next(iter(entries))}], "next_action": "Read current state"}
    errors = legacy.validate_v2_content(plan_text.replace(FORMAT, "plan-your-project/v2", 1), legacy.render_status(stub, language, pm.get("frozen_at", ""), int(pm.get("plan_revision", "0"))))
    require(not errors, "; ".join(errors))
    return pm, body, entries


def validate_state(state, entries, root, check_refs=True):
    exact(state, STATE_KEYS, "status")
    for key in ("summary", "next_action", "current_milestone"):
        text(state[key], key)
    require(state["state"] in ("planned", "in_progress", "blocked", "complete"), "invalid state")
    require(state["current_milestone"] in entries, "current_milestone absent from PLAN")
    for key in ("blockers", "must_read", "authorization"):
        strings(state[key], key, key in ("must_read", "authorization"))
    require(len(state["must_read"]) == len(set(state["must_read"])) and "research/PLAN.md" in state["must_read"], "must_read must uniquely include research/PLAN.md")
    for value in state["must_read"]:
        safe_relative(root, value, exists=check_refs)
    evidence = {}
    for section, keys in (("milestones", MILESTONE_KEYS), ("running_tasks", TASK_KEYS), ("evidence", EVIDENCE_KEYS)):
        require(isinstance(state[section], list), f"{section} must be a list")
        ids = set()
        for item in state[section]:
            exact(item, keys, section)
            for key in keys:
                if key == "evidence":
                    strings(item[key], "evidence IDs")
                else:
                    text(item[key], section + "." + key, empty=key == "acceptance_basis")
            require(re.fullmatch(IDENTIFIER, item["id"]) and item["id"] not in ids, f"invalid or duplicate {section} ID")
            ids.add(item["id"])
    for item in state["evidence"]:
        require(item["source"] in ("observed", "historical", "unverified"), "evidence source must be observed/historical/unverified")
        # External references are descriptions, never commands or implicit network access.
        external = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", item["ref"]) or Path(item["ref"]).is_absolute()
        if not external:
            safe_relative(root, item["ref"], exists=check_refs and item["source"] != "unverified")
        evidence[item["id"]] = item
    require({m["id"] for m in state["milestones"]} == set(entries), "STATUS milestones must exactly match PLAN IDs")
    for milestone in state["milestones"]:
        require(milestone["execution"] in ("pending", "running", "done"), "invalid execution status")
        require(milestone["validation"] in ("not_run", "passed", "failed"), "invalid validation status")
        require(milestone["acceptance"] in ("pending", "accepted", "rejected"), "invalid acceptance status")
        require(milestone["conclusion"] in ("not_applicable", "supported", "unverified"), "invalid research conclusion")
        require(all(e in evidence for e in milestone["evidence"]), "unknown milestone evidence ID")
        supported = any(evidence[e]["source"] != "unverified" for e in milestone["evidence"])
        if milestone["validation"] in ("passed", "failed") or milestone["conclusion"] == "supported":
            require(supported, "validation/conclusion requires observed or historical evidence")
        if milestone["acceptance"] == "accepted":
            require(milestone["execution"] == "done" and milestone["validation"] == "passed" and bool(milestone["acceptance_basis"].strip()) and supported, "accepted milestone requires work done, passed validation, evidence and acceptance_basis")
    if state["state"] == "blocked":
        require(state["blockers"], "blocked state requires blockers")
    if state["state"] == "complete":
        require(all(m["acceptance"] == "accepted" for m in state["milestones"]) and not state["running_tasks"] and not state["blockers"], "complete requires every milestone accepted, no running tasks and no blockers")
    require(not legacy.contains_placeholder(json.dumps(state, ensure_ascii=False)), "STATUS contains unresolved placeholders")


def initial_state(plan):
    return {"summary": "计划已冻结，执行尚未开始。", "state": "planned", "current_milestone": plan["milestones"][0]["id"],
            "milestones": [empty_milestone(m["id"]) for m in plan["milestones"]], "running_tasks": [], "blockers": [], "next_action": plan["next_action"], "must_read": ["research/PLAN.md"], "evidence": [], "authorization": ["仅执行已冻结计划及用户已授权事项；新目标和外部操作另按用户指令。"]}


def empty_milestone(identifier):
    return {"id": identifier, "execution": "pending", "validation": "not_run", "acceptance": "pending", "summary": "尚未开始 / not started", "evidence": [], "acceptance_basis": "", "conclusion": "not_applicable"}


def render_status(state, revision, status_revision, date):
    metadata = ["---", f"workspace_format: {FORMAT}", "record: STATUS", f"plan_revision: {revision}", f"status_revision: {status_revision}", f"state: {state['state']}", f"current_milestone: {state['current_milestone']}", f"last_updated: {date}", "tracking: key_events", "---", "", "# Status", ""]
    values = [state["summary"], render_records(state["milestones"], MILESTONE_KEYS), render_records(state["running_tasks"], TASK_KEYS), legacy.bullets(state["blockers"], "(none)"), state["next_action"], legacy.bullets(state["must_read"]), render_records(state["evidence"], EVIDENCE_KEYS), legacy.bullets(state["authorization"])]
    return "\n".join(metadata) + "\n\n".join(f"## {h}\n{value}" for h, value in zip(HEADINGS, values)) + "\n"


def parse_status(raw):
    sm, body = legacy.metadata(raw)
    exact(sm, ("workspace_format", "record", "plan_revision", "status_revision", "state", "current_milestone", "last_updated", "tracking"), "STATUS metadata")
    require(sm["workspace_format"] == FORMAT and sm["record"] == "STATUS" and sm["tracking"] == "key_events", "invalid STATUS format or tracking")
    for field in ("plan_revision", "status_revision"):
        require(re.fullmatch(r"[1-9][0-9]*", sm[field]), f"invalid {field}")
    require(legacy.valid_iso_date(sm["last_updated"]), "invalid last_updated")
    require(re.findall(r"(?m)^# (.+)$", body) == ["Status"], "invalid STATUS title")
    parts = sections(body, HEADINGS)
    return sm, {"summary": parts["Summary"], "state": sm["state"], "current_milestone": sm["current_milestone"], "milestones": parse_records(parts["Milestones"], MILESTONE_KEYS), "running_tasks": parse_records(parts["Running Tasks"], TASK_KEYS), "blockers": parse_list(parts["Blockers"]), "next_action": parts["Next Action"], "must_read": parse_list(parts["Must Read"]), "evidence": parse_records(parts["Evidence"], EVIDENCE_KEYS), "authorization": parse_list(parts["Authorization"])}


def record_files(root):
    base = root / "research/records"
    if not base.exists():
        return []
    require(base.is_dir() and base.resolve().is_relative_to(root.resolve()), "records directory escapes workspace")
    found = []
    for kind in base.iterdir():
        require(kind.name in ("decisions", "reviews", "retrospectives", "handoffs", "checkpoints") and kind.is_dir(), "unknown records kind")
        require(kind.resolve().is_relative_to(root.resolve()), "record kind escapes workspace")
        for path in kind.iterdir():
            io.ensure_within(root, path)
            require(re.fullmatch(r"\d{4}-\d{2}-\d{2}-" + SLUG + r"\.md", path.name) and legacy.valid_iso_date(path.name[:10]), "invalid record filename")
            raw = path.read_text(encoding="utf-8")
            require(raw.strip() and not legacy.contains_placeholder(raw), "empty record or unresolved placeholder")
            found.append((kind.name, path, raw))
    return found


def checkpoint_metadata(root):
    result = {}
    for kind, path, raw in record_files(root):
        if kind != "checkpoints":
            continue
        meta, body = legacy.metadata(raw)
        exact(meta, ("workspace_format", "record", "kind", "id", "date", "plan_revision", "status_revision", "source_plan_hash", "source_status_hash", "request_hash"), "CHECKPOINT metadata")
        require(meta.get("workspace_format") == FORMAT and meta.get("record") == "CHECKPOINT", "invalid checkpoint metadata")
        require(re.fullmatch(SLUG, meta.get("id", "")) and meta["id"] not in result, "invalid or duplicate checkpoint ID")
        for key in ("request_hash", "source_plan_hash", "source_status_hash"):
            require(re.fullmatch(r"[a-f0-9]{64}", meta.get(key, "")), "invalid checkpoint " + key)
        require(meta.get("kind") in ("checkpoint", "refreeze", "migration"), "invalid checkpoint kind")
        for key in ("plan_revision", "status_revision"):
            require(re.fullmatch(r"[1-9][0-9]*", meta.get(key, "")), "invalid checkpoint revision")
        require(meta.get("date") == path.name[:10] and path.name == f"{meta['date']}-{meta['id']}.md", "checkpoint ID/date mismatch")
        require(len(re.findall(r"(?m)^# \S.*$", body)) == 1, "checkpoint requires one nonempty title")
        parts = sections(body, ("Changes", "Evidence"))
        require(parse_list(parts["Changes"]), "checkpoint requires nonempty changes")
        evidence_body = parts["Evidence"].split("\n\n本记录仅适用于", 1)[0]
        for line in parse_list(evidence_body):
            require(re.fullmatch(IDENTIFIER + r" \[(observed|historical|unverified)\] .+ \| code=.+ \| checked=.+", line), "invalid checkpoint evidence reference")
        result[meta["id"]] = (meta, path)
    return result


def read_workspace(root, allow_pending=False, check_refs=True):
    require(allow_pending or not io.pending_transaction(root), "unfinished transaction: run recover before trusting state or writing")
    layout, messages = legacy.classify_layout(root)
    require(layout == "v2", f"{layout} layout is read-only or unavailable: {'; '.join(messages)}")
    pp, sp = paths(root)
    before = {"plan": io.hash_file(pp), "status": io.hash_file(sp)}
    plan_raw, status_raw = pp.read_text(encoding="utf-8"), sp.read_text(encoding="utf-8")
    pm, body, entries = read_plan(plan_raw)
    if pm["workspace_format"] == "plan-your-project/v2":
        errors = legacy.validate_v2(root)
        if not check_refs:
            errors = [error for error in errors if "STATUS must_read path is not an existing file:" not in error]
        require(not errors, "; ".join(errors))
        sm, st = legacy.metadata(status_raw)
        state = None
    else:
        sm, state = parse_status(status_raw)
        require(pm["plan_revision"] == sm["plan_revision"], "PLAN/STATUS revision mismatch")
        validate_state(state, entries, root, check_refs=check_refs)
        records = checkpoint_metadata(root)
        require(all(int(m[0]["plan_revision"]) <= int(pm["plan_revision"]) and int(m[0]["status_revision"]) <= int(sm["status_revision"]) for m in records.values()), "checkpoint is newer than current state")
    after = {"plan": io.hash_file(pp), "status": io.hash_file(sp)}
    require(before == after and (allow_pending or not io.pending_transaction(root)), "state changed during read; retry resume")
    return {"format": pm["workspace_format"], "project_name": re.search(r"(?m)^# (.+)$", body).group(1), "plan_revision": int(pm["plan_revision"]), "status_revision": int(sm.get("status_revision", "0")), "hashes": after, "status": state, "plan_metadata": pm, "status_metadata": sm, "plan_body": body, "milestone_entries": entries, "plan_text": plan_raw, "status_text": status_raw}


def current_expected(root, args):
    require(args.expected_plan_hash and args.expected_status_hash, "writes require --expected-plan-hash and --expected-status-hash from resume")
    for value in (args.expected_plan_hash, args.expected_status_hash):
        require(re.fullmatch(r"[a-f0-9]{64}", value), "invalid expected hash")
    pp, sp = paths(root)
    return {pp: args.expected_plan_hash, sp: args.expected_status_hash}


def commit(root, files, expected):
    for path in files:
        if path not in expected:
            expected[path] = None
    io.commit_files(root, files, expected, lambda: read_workspace(root, allow_pending=True))


def record_text(kind, request, snapshot, plan_revision, status_revision, changes, state):
    previous = {e["id"]: e for e in (snapshot.get("status") or {}).get("evidence", [])}
    evidence = [f"{e['id']} [{e['source']}] {e['ref']} | code={e['code_ref']} | checked={e['checked_at']}" for e in state["evidence"] if previous.get(e["id"]) != e]
    return "\n".join(["---", f"workspace_format: {FORMAT}", "record: CHECKPOINT", f"kind: {kind}", f"id: {request['id']}", f"date: {request['date']}", f"plan_revision: {plan_revision}", f"status_revision: {status_revision}", f"source_plan_hash: {snapshot['hashes']['plan']}", f"source_status_hash: {snapshot['hashes']['status']}", f"request_hash: {digest(request)}", "---", "", "# " + request["summary"], "", "## Changes", legacy.bullets(changes), "", "## Evidence", legacy.bullets(evidence, "(none)"), "", "本记录仅适用于上述计划修订与截止日期；较新 STATUS 和用户决定优先。", ""])


def check_request(request):
    require(re.fullmatch(SLUG, request.get("id", "")), "id must be lowercase hyphenated slug")
    require(legacy.valid_iso_date(request.get("date", "")), "date must be YYYY-MM-DD")
    text(request.get("summary"), "summary")


def duplicate(root, request):
    found = checkpoint_metadata(root).get(request["id"])
    if found:
        require(found[0]["request_hash"] == digest(request), "checkpoint ID already exists with different content")
        return True
    return False


def require_new(snapshot):
    require(snapshot["format"] == FORMAT, "v2 workspace is read-only; preview enable-tracking first")


def checkpoint(root, args):
    request = load_json(args.update_file)
    exact(request, ("id", "date", "summary", "changes", "status"), "checkpoint request")
    check_request(request)
    strings(request["changes"], "changes", True)
    snapshot = read_workspace(root, check_refs=False)
    require_new(snapshot)
    if duplicate(root, request):
        return {"result": "unchanged", "id": request["id"]}
    state = request["status"]
    validate_state(state, snapshot["milestone_entries"], root)
    require(state != snapshot["status"], "no new state facts: do not create a checkpoint for repeated checks")
    pp, sp = paths(root)
    revision = snapshot["status_revision"] + 1
    record = root / f"research/records/checkpoints/{request['date']}-{request['id']}.md"
    files = {sp: render_status(state, snapshot["plan_revision"], revision, request["date"]), record: record_text("checkpoint", request, snapshot, snapshot["plan_revision"], revision, request["changes"], state)}
    commit(root, files, current_expected(root, args))
    return {"result": "updated", "id": request["id"], "status_revision": revision}


def refreeze(root, args):
    plan = legacy.load_plan(args.plan_file)
    snapshot = read_workspace(root)
    require_new(snapshot)
    request = {"id": args.id, "date": args.date, "summary": args.summary, "plan": plan, "affected": sorted(set(args.affected_milestone or []))}
    check_request(request)
    if duplicate(root, request):
        return {"result": "unchanged", "id": request["id"]}
    revision = snapshot["plan_revision"] + 1
    language = snapshot["plan_metadata"]["language"]
    rendered = legacy.render_plan(plan, language, args.date, revision).replace("workspace_format: plan-your-project/v2\n", f"workspace_format: {FORMAT}\n", 1)
    _, body, entries = read_plan(rendered)
    old = snapshot["milestone_entries"]
    require(set(request["affected"]) <= set(entries) | set(old), "unknown affected milestone")
    critical = ("问题", "目标", "成功标准", "范围", "约束", "选定方案", "冻结决策") if language == "zh" else ("Problem", "Goal", "Success Criteria", "Scope", "Constraints", "Selected Approach", "Locked Decisions")
    if any(legacy.section_body(body, h) != legacy.section_body(snapshot["plan_body"], h) for h in critical):
        require(request["affected"], "scope/goal/decision changes require explicit --affected-milestone")
    affected = set(request["affected"]) | {key for key in entries if entries[key] != old.get(key)}
    state = copy.deepcopy(snapshot["status"])
    previous = {m["id"]: m for m in state["milestones"]}
    state["milestones"] = []
    for key in entries:
        milestone = previous.get(key, empty_milestone(key))
        if key in affected:
            milestone.update(validation="not_run", acceptance="pending", acceptance_basis="", summary="计划已修订，既有实现与证据需要按新验收复核。")
            if milestone["conclusion"] != "not_applicable":
                milestone["conclusion"] = "unverified"
        state["milestones"].append(milestone)
    state["summary"] = args.summary
    next_heading = "下一步" if language == "zh" else "Next Action"
    if plan["next_action"] != legacy.section_body(snapshot["plan_body"], next_heading):
        state["next_action"] = plan["next_action"]
    current = next((m for m in state["milestones"] if m["id"] == state["current_milestone"]), None)
    if current is None or (current["acceptance"] == "accepted" and any(m["acceptance"] != "accepted" for m in state["milestones"])):
        state["current_milestone"] = next((m["id"] for m in state["milestones"] if m["acceptance"] != "accepted"), next(iter(entries)))
    if affected and state["state"] == "complete":
        state["state"] = "in_progress"
    validate_state(state, entries, root)
    changes = [args.summary, "Affected/revalidate: " + (", ".join(sorted(affected)) or "none"), "Removed (historical results retained here): " + (", ".join(sorted(set(old) - set(entries))) or "none")]
    for milestone in snapshot["status"]["milestones"]:
        if milestone["id"] in affected or milestone["id"] not in entries:
            changes.append(f"Previous {milestone['id']}: {milestone['execution']}/{milestone['validation']}/{milestone['acceptance']}; {milestone['summary']}; evidence={','.join(milestone['evidence'])}; basis={milestone['acceptance_basis']}")
    pp, sp = paths(root)
    sr = snapshot["status_revision"] + 1
    cp = root / f"research/records/checkpoints/{args.date}-{args.id}.md"
    commit(root, {pp: rendered, sp: render_status(state, revision, sr, args.date), cp: record_text("refreeze", request, snapshot, revision, sr, changes, state)}, current_expected(root, args))
    return {"result": "refrozen", "plan_revision": revision, "status_revision": sr, "affected": sorted(affected)}


def git_facts(root):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    result = {}
    for name, command in (("head", ["rev-parse", "HEAD"]), ("branch", ["branch", "--show-current"]), ("worktree", ["status", "--short", "--untracked-files=normal"])):
        try:
            proc = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), *command], capture_output=True, text=True, timeout=8, env=env)
            result[name] = proc.stdout.strip()[:8000] if proc.returncode == 0 else "unavailable"
        except (OSError, subprocess.TimeoutExpired):
            result[name] = "unavailable"
    return result


def resume(root):
    layout, messages = legacy.classify_layout(root)
    if io.pending_transaction(root):
        return {"result": "recovery_required", "read_only": True, "warnings": ["Pending transaction: run recover; do not trust a partial PLAN/STATUS pair."]}
    if layout in ("v1", "mixed"):
        return {"result": "legacy_read_only", "format": layout, "warnings": messages + ["Do not migrate or update v1/mixed layouts with this tool."], "git": git_facts(root)}
    snapshot = read_workspace(root, check_refs=False)
    warnings = ["Git facts were checked locally; remote processes and remote evidence were not inspected. Historical passes are not current-code passes."]
    if snapshot["format"] != FORMAT:
        warnings.append("Legacy v2 is read-only until explicit enable-tracking migration; per-milestone acceptance is unknown.")
    if len(snapshot["status_text"].splitlines()) > 100:
        warnings.append("STATUS exceeds the ~100-line target; shorten prose/must_read and link history without dropping important facts.")
    state = snapshot["status"]
    if state:
        local_refs = state["must_read"] + [e["ref"] for e in state["evidence"] if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", e["ref"]) and not Path(e["ref"]).is_absolute()]
        for reference in dict.fromkeys(local_refs):
            if not (root / reference).is_file():
                warnings.append(f"Missing reference: {reference}. Recorded completion is unverified at the current site; investigate and checkpoint the corrected evidence/status before continuing.")
    if state and len(state["must_read"]) > 5:
        warnings.append("Review the must_read list; keep only PLAN and materials needed for the next action.")
    if state and state["running_tasks"]:
        warnings.append("Recorded tasks may still be running. Verify their environment/task identifiers before starting any duplicate.")
    git = git_facts(root)
    for item in state["evidence"] if state else []:
        if item["source"] == "historical" or item["code_ref"] != git["head"]:
            warnings.append(f"Evidence {item['id']} applies to {item['code_ref']} ({item['source']}); recheck applicability to the current worktree.")
    return {key: snapshot[key] for key in ("format", "project_name", "plan_revision", "status_revision", "hashes", "status")} | {"workspace_root": str(root), "result": "resumed", "warnings": warnings, "git": git, "legacy_status": snapshot["status_text"] if state is None else None, "read_order": ["project rules / AGENTS.md", "research/STATUS.md", "research/PLAN.md", "current must_read", "relevant live facts"]}


def handoff(root, args):
    snapshot = read_workspace(root, check_refs=False)
    state = snapshot["status"]
    lines = ["# 项目交接摘要：" + snapshot["project_name"], "", f"截止时间：{dt.datetime.now(dt.timezone.utc).isoformat()}", f"源格式：{snapshot['format']}；PLAN 修订 {snapshot['plan_revision']}；STATUS 修订 {snapshot['status_revision']}", f"PLAN SHA-256：{snapshot['hashes']['plan']}", f"STATUS SHA-256：{snapshot['hashes']['status']}", "", "## 接续规则", "先读项目规则与 STATUS，再读 PLAN 和下一动作必要材料；核对分支、HEAD、未提交改动及相关产物/运行状态。历史交接不能覆盖较新用户决定。", "本摘要不授予额外实验、发布或外部操作权限；仅继续已授权工作。未访问的服务器仍为未现场核验，不按旧报告宣布任务结束。", "", "## 目标与冻结边界"]
    language = snapshot["plan_metadata"]["language"]
    for heading in (("目标", "选定方案", "成功标准", "范围", "约束", "冻结决策", "里程碑") if language == "zh" else ("Goal", "Selected Approach", "Success Criteria", "Scope", "Constraints", "Locked Decisions", "Milestones")):
        lines += [f"### {heading}", legacy.section_body(snapshot["plan_body"], heading) or "(none)"]
    checked = resume(root)
    lines += ["", "## 当前进展、证据与下一步", snapshot["status_text"].split("\n---\n", 1)[1].strip(), "", "## 现场核验", "```json", json.dumps(checked["git"], ensure_ascii=False, indent=2), "```", "Git 事实为本次读取；远端任务、日志和实验结果未自动核验。", legacy.bullets(checked["warnings"])]
    # Include bounded excerpts so a file-less recipient can evaluate linked evidence.
    for evidence in (state or {}).get("evidence", []):
        lines += ["", f"### 证据 {evidence['id']} [{evidence['source']}]", evidence["summary"], f"来源：{evidence['ref']}；适用版本：{evidence['code_ref']}；核验时间：{evidence['checked_at']}"]
    lines += ["", "## 网页 AI 待同步更新", "没有仓库写入能力时，将建议标为“待同步更新”，不得宣称已保存。返回上述源 PLAN/STATUS 哈希、变化、证据来源、适用代码版本、下一步和授权依据。", "文件型 AI 接手后重新读取并核对两份哈希；一致才转为 checkpoint。哈希不同则先对比新状态并重新整理，不覆盖新决定。", "跨电脑仍依赖已有 Git 或文件同步；本工具不提交、不推送、不监控后台任务。", ""]
    output = "\n".join(lines)
    if args.output:
        target = safe_relative(root, args.output, exists=False)
        require(not target.exists(), "handoff output already exists; use a new path")
        with io.WorkspaceLock(root):
            expected = {paths(root)[0]: snapshot["hashes"]["plan"], paths(root)[1]: snapshot["hashes"]["status"], target: None}
            io.commit_files(root, {target: output}, expected, lambda: read_workspace(root, allow_pending=True, check_refs=False))
        return {"result": "saved", "output": str(target)}
    return output


def merge_protocol(old, template):
    require(old.count(START) == old.count(END) and old.count(START) <= 1, "malformed/duplicate AGENTS managed block")
    if START in old:
        require(old.index(START) < old.index(END), "malformed AGENTS managed block")
        return old[:old.index(START)] + template.rstrip() + old[old.index(END) + len(END):]
    return old.rstrip() + ("\n\n" if old.strip() else "") + template.rstrip() + "\n"


def enable_tracking(root, args):
    snapshot = read_workspace(root)
    pp, sp = paths(root)
    templates = Path(__file__).resolve().parents[1] / "assets"
    ap, cp = root / "AGENTS.md", root / "CLAUDE.md"
    io.ensure_within(root, ap)
    io.ensure_within(root, cp)
    old_agents = ap.read_bytes().decode("utf-8") if ap.exists() else ""
    new_agents = merge_protocol(old_agents, (templates / "AGENTS_tracking.md").read_text(encoding="utf-8"))
    files = {ap: new_agents} if new_agents != old_agents else {}
    if args.claude_bridge:
        old_claude = cp.read_bytes().decode("utf-8") if cp.exists() else ""
        if not re.search(r"(?m)^@AGENTS\.md\s*$", old_claude):
            files[cp] = old_claude.rstrip() + ("\n\n" if old_claude.strip() else "") + "@AGENTS.md\n"
    is_old = snapshot["format"] != FORMAT
    preview = {"result": "preview", "from": snapshot["format"], "to": FORMAT, "hashes": snapshot["hashes"], "changes": [str(p.relative_to(root)) for p in files], "migration_requires_reviewed_status_file": is_old, "notes": ["No files were written. Existing history and rules will be preserved. Explicit --apply authorizes backup and conversion."]}
    preview["diffs"] = {str(path.relative_to(root)): "".join(difflib.unified_diff((path.read_bytes().decode("utf-8") if path.exists() else "").splitlines(keepends=True), value.splitlines(keepends=True), fromfile=str(path.relative_to(root)), tofile=str(path.relative_to(root)))) for path, value in files.items()}
    if is_old:
        preview["changes"] += ["research/PLAN.md marker", "research/STATUS.md", "migration checkpoint and backups"]
        preview["legacy_status"] = snapshot["status_text"]
        preview["status_template"] = {"summary": "需根据旧状态和证据逐项核对后填写。", "state": snapshot["status_metadata"]["state"] if snapshot["status_metadata"]["state"] != "complete" else "in_progress", "current_milestone": snapshot["status_metadata"]["current_milestone"], "milestones": [empty_milestone(key) for key in snapshot["milestone_entries"]], "running_tasks": [], "blockers": [], "next_action": "核对旧状态与当前证据后确定下一步", "must_read": ["research/PLAN.md"], "evidence": [], "authorization": ["迁移仅整理已授权工作事实；未核实的旧验收不能标为已接受。"]}
        if args.status_file:
            proposed = load_json(args.status_file)
            validate_state(proposed, snapshot["milestone_entries"], root)
            for path, original, value in ((pp, snapshot["plan_text"], snapshot["plan_text"].replace("workspace_format: plan-your-project/v2\n", f"workspace_format: {FORMAT}\n", 1)), (sp, snapshot["status_text"], render_status(proposed, snapshot["plan_revision"], 1, args.date))):
                preview["diffs"][str(path.relative_to(root))] = "".join(difflib.unified_diff(original.splitlines(keepends=True), value.splitlines(keepends=True), fromfile=str(path.relative_to(root)), tofile=str(path.relative_to(root))))
        else:
            preview["notes"].append("Review/fill status_template, then preview again with --status-file to inspect the exact PLAN/STATUS diff before applying.")
    if not args.apply:
        return preview
    if not is_old and not files:
        return {"result": "unchanged", "format": FORMAT}
    expected = current_expected(root, args)
    # Backups are regular UTF-8 originals inside the workspace, committed with conversion.
    tag = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = root / ".plan-your-project-backups" / tag
    originals = {p: p.read_bytes().decode("utf-8") for p in (pp, sp, ap, cp) if p.exists()}
    for path, raw in originals.items():
        files[backup / path.relative_to(root)] = raw
    if is_old:
        require(args.status_file, "v2 apply requires --status-file reviewed against old progress, blockers and evidence; preview supplies a template")
        state = load_json(args.status_file)
        validate_state(state, snapshot["milestone_entries"], root)
        request = {"id": "enable-tracking-" + tag.lower(), "date": args.date, "summary": "启用 v2.1 关键节点记录；历史状态以备份保留。", "status": state}
        files[pp] = snapshot["plan_text"].replace("workspace_format: plan-your-project/v2\n", f"workspace_format: {FORMAT}\n", 1)
        files[sp] = render_status(state, snapshot["plan_revision"], 1, args.date)
        record = root / f"research/records/checkpoints/{args.date}-{request['id']}.md"
        changes = ["Legacy originals preserved at " + str(backup.relative_to(root)), "Migrated using reviewed state; no execution/acceptance inferred automatically."]
        files[record] = record_text("migration", request, snapshot, snapshot["plan_revision"], 1, changes, state)
    for path in (ap, cp):
        if path in files:
            expected[path] = io.hash_file(path)
    commit(root, files, expected)
    return {"result": "enabled", "format": FORMAT, "backup": str(backup)}


def initialize(root, args):
    layout, _ = legacy.classify_layout(root)
    require(layout == "empty", "init only accepts an empty planning workspace; use resume or explicit enable-tracking")
    plan = legacy.load_plan(args.plan_file)
    rendered = legacy.render_plan(plan, args.language, args.date, 1).replace("workspace_format: plan-your-project/v2\n", f"workspace_format: {FORMAT}\n", 1)
    _, _, entries = read_plan(rendered)
    state = initial_state(plan)
    validate_state(state, entries, root, check_refs=False)
    pp, sp = paths(root)
    if args.dry_run:
        return {"result": "preview", "format": FORMAT, "files": [str(pp), str(sp)]}
    commit(root, {pp: rendered, sp: render_status(state, 1, 1, args.date)}, {pp: None, sp: None})
    return {"result": "initialized", "format": FORMAT}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    for name in ("init", "resume", "validate", "checkpoint", "refreeze", "handoff", "enable-tracking", "recover"):
        sub = commands.add_parser(name)
        sub.add_argument("--workspace-root", type=Path, required=True)
        sub.add_argument("--json", action="store_true")
        if name in ("init", "refreeze", "enable-tracking"):
            sub.add_argument("--date", type=legacy.parse_date, default=dt.date.today().isoformat())
        if name in ("init", "refreeze"):
            sub.add_argument("--plan-file", required=True)
        if name == "init":
            sub.add_argument("--language", choices=("zh", "en"), default="zh")
            sub.add_argument("--dry-run", action="store_true")
        if name in ("checkpoint", "refreeze", "enable-tracking"):
            sub.add_argument("--expected-plan-hash")
            sub.add_argument("--expected-status-hash")
        if name == "checkpoint":
            sub.add_argument("--update-file", required=True)
        if name == "refreeze":
            sub.add_argument("--id", required=True)
            sub.add_argument("--summary", required=True)
            sub.add_argument("--affected-milestone", action="append")
        if name == "handoff":
            sub.add_argument("--output", help="Workspace-relative new Markdown file. Omit to print only.")
        if name == "enable-tracking":
            sub.add_argument("--apply", action="store_true")
            sub.add_argument("--status-file")
            sub.add_argument("--claude-bridge", action="store_true")
    return p


def dispatch(root, args):
    command = args.command
    if command == "init":
        return initialize(root, args)
    if command == "resume":
        return resume(root)
    if command == "validate":
        snap = read_workspace(root)
        return {"result": "valid", "format": snap["format"], "plan_revision": snap["plan_revision"], "status_revision": snap["status_revision"]}
    if command == "checkpoint":
        return checkpoint(root, args)
    if command == "refreeze":
        return refreeze(root, args)
    if command == "handoff":
        return handoff(root, args)
    if command == "enable-tracking":
        return enable_tracking(root, args)
    if command == "recover":
        return {"result": "recovered" if io.recover(root) else "unchanged"}
    raise Error("unknown command")


def main(argv=None):
    args = parser().parse_args(argv)
    root = args.workspace_root.resolve()
    write = args.command in ("checkpoint", "refreeze", "recover") or (args.command == "init" and not args.dry_run) or (args.command == "enable-tracking" and args.apply)
    try:
        if write:
            with io.WorkspaceLock(root):
                result = dispatch(root, args)
        else:
            result = dispatch(root, args)
        print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
        return 0
    except (Error, io.WorkspaceIOError, OSError, UnicodeError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"result": "error", "message": str(exc)}, ensure_ascii=False) if args.json else f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
