---
description: Apply the ADR-009 triage checklist to a GitHub issue.
argument-hint: "[issue-number]"
---

Triage issue **#$ARGUMENTS** against the checklist in
[`docs/project-management.md`](../../docs/project-management.md) (ADR-009).

Verify and, where missing, set:

1. **Issue type** — exactly one of Epic / Feature / Task / Spike / Bug.
2. **Milestone** — the release-versioned milestone, or the `backlog` label if
   unscheduled.
3. **`component:*` label(s)** — which part(s) of the codebase it touches.
4. **`phase-*` label** — the thematic roadmap phase, if applicable.
5. **Parent Epic** — link it as a sub-issue where relevant.
6. **Board** — add it to Project #11; set **Effort** if it's entering active
   planning.

Report what was already correct and what you changed. Do not implement the
issue — this command only triages.
