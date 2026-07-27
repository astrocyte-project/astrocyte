---
description: Pick up a GitHub issue and implement it end-to-end via the finisher persona.
argument-hint: "[issue-number]"
---

Invoke the **finisher** persona (`.github/agents/finisher.md`) to implement issue
**#$ARGUMENTS**.

If no issue number was given, list the open, unassigned issues in the current
milestone and ask which one to pick up.

Follow the finisher workflow: read the issue and `CLAUDE.md`, check for existing
work, branch, post an implementation-plan comment, implement with tests, run
`make check`, update the CHANGELOG, and open a PR that `Closes #$ARGUMENTS`.

When done, report the branch name, the plan-comment URL, and the PR URL.
