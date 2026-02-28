# Mini-TPU Project — Agent Entry Point

The active RTL subproject is `tpu/`. **Read `tpu/CLAUDE.md` first** — it is the single
source of truth for architecture, working conventions, execution rules, and verification.

Then read in order:
1. `tpu/PLAN.md` — task list by priority (P0–P3); each task lists exact files to touch
2. `tpu/PROGRESS.md` — what was last done and current open issues

That is sufficient context to start working. Do not ask for more orientation — pick the
highest-priority unresolved task in PLAN.md and follow the Execution Rules in CLAUDE.md.

## Context Management

Files are organized as modular, composable units for selective context loading.
Agents MUST swap in only the specific doc/src/test files relevant to the current task.
Do NOT truncate or skip content within files to save context — instead, choose which
files to load. Every file is designed to be self-contained and independently useful.

Load order: tpu/CLAUDE.md (always) → relevant docs/*.md → relevant src/ → relevant test/.
See tpu/CLAUDE.md §Context Loading Guide for the mapping table.
