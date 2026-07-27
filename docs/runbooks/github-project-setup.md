# Runbook: GitHub Project setup

How to stand up and maintain the declarative project-management sync. See
[docs/project-management.md](../project-management.md) for the model itself.

## Prerequisites

- Maintainer access to the `astrocyte-project` org.
- The [`gh`](https://cli.github.com/) CLI, authenticated with a session that has
  `admin:org` and `project` scopes (`gh auth refresh -s admin:org,project`).

## What the sync manages

[`scripts/project-sync.sh`](../../scripts/project-sync.sh) reconciles, **non-
destructively**, from [`.github/project.yml`](../../.github/project.yml):

- repo **labels** (create/update/rename via `from:`),
- release **milestones** (create/update),
- org **issue types** (validate-only),
- org **Project #11** custom fields (validate-only).

It never deletes anything absent from the spec.

## Running it locally

```bash
bash scripts/project-sync.sh
```

Verify:

```bash
gh label list
gh api repos/astrocyte-project/astrocyte/milestones --jq '.[].title'
gh project field-list 11 --owner astrocyte-project
```

## Running it in CI (unattended)

The [`project-sync`](../../.github/workflows/project-sync.yml) workflow runs on
pushes to `main` that touch the spec, and on manual dispatch. It needs a
maintainer PAT because org issue types and org Projects cannot be written by the
default `GITHUB_TOKEN`.

1. Create a **fine-grained or classic PAT** with `repo`, `project`, and org
   read/write (`admin:org`) scopes.
2. Add it as the repo secret **`PROJECT_ADMIN_TOKEN`**
   (`gh secret set PROJECT_ADMIN_TOKEN`).
3. Trigger a run: `gh workflow run project-sync.yml` (or push a spec change).

Until the secret exists, the workflow still runs but exits `0` with a warning
and makes no changes.

## Auto-add automation

New issues and pull requests are added to the board automatically by the
Project's **built-in workflows** (Project ⚙ → Workflows), not a repo Action:

- **Auto-add to project** — adds matching new items in this repo to the board.
- **Auto-add sub-issues to project** — pulls in sub-issues of tracked issues.

These are configured in the Projects UI and can't be codified in `project.yml`.
Confirm they're enabled after any board rebuild.

## Board views

Views are created in the Projects UI (the API cannot create or configure them).
The board currently carries:

| View | Layout | Config | Purpose |
|------|--------|--------|---------|
| **By Milestone** | Table | Group by `Milestone` | Release planning across v0.2–v1.0 |
| **By Component** | Table | Slice by `Labels` | Browse work by `component:*` area |
| **Current Sprint** | Board | Filter `milestone:"v0.2 — Foundation & DX"`, columns by `Status` | Active-release kanban |
| **Open Items** | Table | Filter `is:issue -status:Done` | All in-flight issues |
| **Roadmap** | Roadmap | Group by `Milestone` | Timeline via Start/Target Date |

Notes:

- **By Component** uses **Slice by Labels** (not Group by) because an issue can
  carry several `component:*` labels; the slice sidebar filters to one at a time.
- **Current Sprint** approximates a sprint with the *active release milestone* —
  update its filter (`milestone:"…"`) when rolling from v0.2 to v0.3, etc. If the
  team later adopts time-boxed sprints, add an `Iteration` field (⚙ → New field)
  and switch the filter to `iteration:@current` (and add the field to
  `.github/project.yml`).
- After editing any view, use the view's ▾ menu → **Save changes**, or it reverts
  on reload.
