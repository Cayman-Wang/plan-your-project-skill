#!/usr/bin/env python3
"""Validate an optional execution handoff document against its required sections.

Standard library only. Works on Windows, macOS and Linux, and in any host that
can run Python (Hermes, Codex CLI, a plain shell).

Exit codes: 0 valid, 1 missing/empty sections, 2 usage or read error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = (
    ("goal", ("目标", "goal", "objective")),
    ("non_goals", ("非目标", "non-goals", "non goals", "out of scope")),
    ("files_and_interfaces", ("涉及文件与接口", "files and interfaces", "files & interfaces")),
    ("constraints", ("不可破坏的约束", "constraints")),
    ("acceptance", ("验收命令", "acceptance", "acceptance commands")),
    ("rollback", ("回退办法", "rollback")),
    ("open_questions", ("未决问题", "open questions", "open decisions")),
)

HEADING = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
NUMBERING = re.compile(r"^\s*\d+\s*[.)、]\s*")
TRAILING = re.compile(r"[\s:：.。]+$")
PLACEHOLDER = re.compile(r"^(?:<[^>]*>|todo|tbd|待补|待填|x{3,})$", re.IGNORECASE)


def normalize_heading(text: str) -> str:
    text = NUMBERING.sub("", text.strip())
    text = TRAILING.sub("", text)
    return re.sub(r"\s+", " ", text).casefold()


def parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            current = normalize_heading(match.group(2))
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def has_content(lines: list[str]) -> bool:
    for raw in lines:
        line = re.sub(r"^[-*+]\s+", "", raw.strip())
        line = re.sub(r"^>\s*", "", line).strip()
        if not line or line.startswith("```"):
            continue
        if line.startswith("|") and set(line) <= set("|-: "):
            continue
        if PLACEHOLDER.match(line):
            continue
        return True
    return False


def validate(text: str) -> dict:
    sections = parse_sections(text)
    missing: list[str] = []
    empty: list[str] = []
    found: dict[str, str] = {}
    for field, aliases in REQUIRED:
        key = next((alias for alias in aliases if alias in sections), None)
        if key is None:
            missing.append(field)
            continue
        found[field] = key
        unreplaced = any(re.search(r"<[^>]*>", line) for line in sections[key])
        if unreplaced or not has_content(sections[key]):
            empty.append(field)
    return {"valid": not missing and not empty, "missing": missing, "empty": empty, "sections": found}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a project handoff document against required sections.")
    parser.add_argument("--file", help="Markdown handoff file; omit to read standard input")
    parser.add_argument("--json", action="store_true", help="Machine-readable result")
    args = parser.parse_args(argv)

    try:
        if args.file:
            raw = Path(args.file).read_bytes()
        else:
            raw = sys.stdin.buffer.read()
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        print(f"handoff_check: cannot read input: {error}", file=sys.stderr)
        return 2

    result = validate(text)
    result["path"] = str(Path(args.file).resolve()) if args.file else None
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["valid"]:
        print(f"OK: {len(REQUIRED)} required sections present")
    else:
        details = []
        if result["missing"]:
            details.append("missing=" + ",".join(result["missing"]))
        if result["empty"]:
            details.append("empty=" + ",".join(result["empty"]))
        print("handoff invalid: " + " ".join(details))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
