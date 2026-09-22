---
name: plan-your-project
description: Plan software or research projects, compare approaches, freeze decisions, and create a minimal planning workspace. Use also to resume existing project work, inspect progress, record requested handoffs, or maintain checkpoints during already-authorized execution in a tracking-enabled workspace. Do not use for unrelated one-off fixes, generic scaffolding, or planning discussions that do not need project records.
---

# Plan Your Project

Use `DISCUSS -> FREEZE -> GENERATE -> MAINTAIN`. Keep the frozen destination separate from observed execution state. Planning does not authorize implementation; enabling progress tracking does not authorize new project work.

## Route The Request

- **DISCUSS:** explore a new, ambiguous, or materially changed project. Inspect relevant user-scoped code, configuration, data, experiment records and papers before asking about discoverable facts. Ask only for owner judgments that affect outcomes, scope, acceptance or significant tradeoffs. Identify evidence, assumptions and open decisions. Discussion and read-only research do not write project records.
- **FREEZE:** confirm a coherent decision set. A lightweight conversation may use a compact view, but the full freezing semantics must be satisfied. Reuse decisions and authorization already supplied; do not ask the user to approve the same action twice.
- **GENERATE:** create the workspace when the user has explicitly authorized saving the frozen plan. Approval of its direction alone is not permission to create files; an instruction that clearly approves the plan and asks to save it supplies both permissions together. Inspect the target first.
- **RESUME / read-only status:** begin with `research/STATUS.md`, then read `research/PLAN.md` and all current `must_read` paths. Compare recorded state with relevant live evidence. Report differences and unknowns without modifying files, including during read-only reviews or resume previews.
- **MAINTAIN:** a request to update status or create a decision, review, retrospective or handoff authorizes that record. In a tracking-enabled v2.1 workspace, already-authorized implementation or research work also authorizes event checkpoints within the agreed tracking scope. Do not repeatedly ask to save routine progress. A pure question or read-only inspection never becomes a write merely because tracking is enabled.

Read [discussion_protocol_zh.md](references/discussion_protocol_zh.md) for DISCUSS / FREEZE; use the [software lens](references/software_lens_zh.md), [research lens](references/research_lens_zh.md), or both as relevant. Read [file_contract_zh.md](references/file_contract_zh.md) before creating or changing records, and [progress_protocol_zh.md](references/progress_protocol_zh.md) before resuming, enabling tracking, recording checkpoints or handing off.

## Keep The Workspace Small

- Default records are `research/PLAN.md` and `research/STATUS.md`, with the current format `plan-your-project/v2.1`. PLAN owns frozen goals, constraints, decisions and acceptance; STATUS owns the current execution snapshot and necessary evidence references.
- Use `scripts/project_state.py` for `init`, `resume`, `validate`, `checkpoint`, `refreeze`, `handoff`, `enable-tracking` and `recover`; consult the file contract and each subcommand's `--help`. The existing `scripts/init_research_workspace.py` entrypoint remains for old-format compatibility; prefer `project_state.py init` for v2.1. `bootstrap_research_workspace.py` is deprecated compatibility support.
- Existing v2 records may be inspected and resumed read-only. Convert and enable tracking only through an explicitly requested `enable-tracking` preview followed by its approved apply operation. Never silently upgrade old records during status inspection. v1, mixed, invalid or interrupted layouts require diagnosis and the applicable recovery path, not overwriting.
- Enabling tracking may merge the bounded [AGENTS tracking block](assets/AGENTS_tracking.md) into the project's existing agent instructions and add the optional [Claude import bridge](assets/CLAUDE_bridge.md). Preview exact changes; preserve unrelated instructions and avoid duplicate blocks or imports. Do not replace the whole instruction file.
- Decision, review, retrospective and handoff records remain lazy. Create them for the requested purpose or an event expressly covered by the enabled tracking agreement. Never pre-create empty directories, placeholders, indexes, prompts or a parallel evidence store. Runtime outputs stay in normal project output locations; records link to them.

## Track Facts, Not Aspirations

Record checkpoints when milestones or acceptance outcomes change, important validation results change, material blockers appear or are resolved, long tasks start/end/fail, or a confirmed decision changes the next action. Before a planned pause, handoff or final response ending authorized work, save any still-unrecorded new progress. Combine related activity into one checkpoint. No-change reads and routine tool calls do not need entries. Record passed, failed, skipped and unavailable verification accurately; distinguish direct observations, reports from others and unverified inference.

One coordinating writer owns shared STATUS. Workers report findings and evidence without independently rewriting it. Before writing, re-read the current revision and use the command's concurrency checks; never silently replace another writer's newer state. Successful atomic file replacement is not proof against stale concurrent edits.

Resume by checking project identity, revisions, current task, evidence relevance, existing changes and referenced handoffs. An older handoff is historical context, not an instruction to roll back newer STATUS. A browser-only AI that cannot edit the repository supplies a clearly labeled **pending synchronization** handoff; it must not say the workspace was updated.

## Revise And Hand Off

A change to the destination—goal, success criteria, scope, locked decisions, milestone acceptance or key constraints—returns to DISCUSS / FREEZE. Preserve previous decisions, explain replacements and obtain the required authorization to write the revision. Reconcile affected milestones explicitly: retain unrelated completed work and its valid evidence; reopen only work whose acceptance or premises changed. Routine progress changes do not rewrite PLAN.

A useful execution handoff carries the approved scope, relevant inputs, locked constraints, current deliverable, acceptance evidence, remaining uncertainty and next action. Prefer the applicable implementation or research-execution skill when available. If none exists and the user has authorized execution, exit the planning workflow and continue through the ordinary implementation workflow, subject to the current runtime mode and permissions. Do not stop authorized work merely because an implementation skill is missing. If only planning was requested, finish with the plan and handoff without executing it.

## Verify And Report

After an allowed write, validate the records, plan/status revision agreement, milestone references, evidence paths, absence of unresolved placeholders and the exact changed-file set. Report what was saved, what remains unverified and the next action. A saved file is not evidence that implementation is complete. Hooks are optional host integrations; the protocol cannot guarantee a checkpoint after abrupt termination or in an agent that never loads the project instructions.
