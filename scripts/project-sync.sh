#!/usr/bin/env bash
#
# project-sync.sh — reconcile GitHub PM objects from .github/project.yml.
#
# Reconciles (non-destructively):
#   * repo labels        (create / update color+description / rename via `from`)
#   * release milestones (create / update description / rename via `from`)
#   * org issue types    (validate-only — warns if any are missing)
#   * org Project fields (validate-only — warns if missing; ensures Effort opts)
#
# It never deletes labels or milestones that are absent from the spec, so
# Dependabot's auto-labels and any ad-hoc milestones are left untouched.
#
# Auth: uses `gh` with the ambient token. In CI, the `project-sync` workflow
# exports PROJECT_ADMIN_TOKEN as GH_TOKEN (a maintainer PAT is required because
# org issue types and org Projects cannot be written by the default token).
# Run locally with a `gh auth login` session that has `admin:org` + `project`.
#
# Usage: bash scripts/project-sync.sh [path/to/project.yml]

set -euo pipefail

SPEC="${1:-.github/project.yml}"
REPO="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------
if [[ ! -f "$SPEC" ]]; then
  echo "::error::spec file not found: $SPEC" >&2
  exit 1
fi

if [[ -n "${PROJECT_ADMIN_TOKEN:-}" ]]; then
  export GH_TOKEN="$PROJECT_ADMIN_TOKEN"
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "::warning::no GitHub auth available (PROJECT_ADMIN_TOKEN unset and no gh session); skipping project sync." >&2
  exit 0
fi

echo "Reconciling PM objects for ${REPO} from ${SPEC}"

# ---------------------------------------------------------------------------
# Emit the spec as line-oriented records so we can loop in pure bash.
# Each helper prints TSV; PyYAML does the parsing.
# ---------------------------------------------------------------------------
py() { python3 -c "$1" "$SPEC"; }

# ----- Labels --------------------------------------------------------------
echo "== Labels =="
py '
import sys, yaml
for l in yaml.safe_load(open(sys.argv[1])).get("labels", []) or []:
    print("\t".join([l["name"], l.get("color",""), l.get("description",""), l.get("from","")]))
' | while IFS=$'\t' read -r name color desc from; do
  # Rename in place if `from` exists as a label and the target does not.
  if [[ -n "$from" ]] && gh label list --repo "$REPO" --limit 200 --json name --jq '.[].name' | grep -qxF "$from"; then
    if gh label list --repo "$REPO" --limit 200 --json name --jq '.[].name' | grep -qxF "$name"; then
      echo "  rename skipped (target exists): $from -> $name"
    else
      echo "  rename: $from -> $name"
      gh label edit "$from" --repo "$REPO" --name "$name" --color "$color" --description "$desc" >/dev/null
      continue
    fi
  fi
  # Create or update.
  if gh label list --repo "$REPO" --limit 200 --json name --jq '.[].name' | grep -qxF "$name"; then
    gh label edit "$name" --repo "$REPO" --color "$color" --description "$desc" >/dev/null
    echo "  update: $name"
  else
    gh label create "$name" --repo "$REPO" --color "$color" --description "$desc" >/dev/null
    echo "  create: $name"
  fi
done

# ----- Milestones ----------------------------------------------------------
echo "== Milestones =="
existing_ms="$(gh api "repos/${REPO}/milestones?state=all&per_page=100" --jq '.[].title')"
ms_number() { # title -> milestone number
  gh api "repos/${REPO}/milestones?state=all&per_page=100" \
    --jq ".[] | select(.title==\"$1\") | .number"
}
py '
import sys, yaml
for m in yaml.safe_load(open(sys.argv[1])).get("milestones", []) or []:
    print("\t".join([m["title"], m.get("description",""), m.get("from","")]))
' | while IFS=$'\t' read -r title desc from; do
  # Rename in place if `from` exists as a milestone and the target does not
  # (preserves issue associations, mirroring the label rename logic).
  if [[ -n "$from" ]] && grep -qxF "$from" <<<"$existing_ms"; then
    if grep -qxF "$title" <<<"$existing_ms"; then
      echo "  rename skipped (target exists): $from -> $title"
    else
      echo "  rename: $from -> $title"
      number="$(ms_number "$from")"
      gh api -X PATCH "repos/${REPO}/milestones/${number}" \
        -f title="$title" -f description="$desc" >/dev/null
      continue
    fi
  fi
  # Create or update.
  if grep -qxF "$title" <<<"$existing_ms"; then
    number="$(ms_number "$title")"
    gh api -X PATCH "repos/${REPO}/milestones/${number}" -f description="$desc" >/dev/null
    echo "  update: $title"
  else
    gh api -X POST "repos/${REPO}/milestones" -f title="$title" -f description="$desc" >/dev/null
    echo "  create: $title"
  fi
done

# ----- Issue types (validate-only) ----------------------------------------
echo "== Issue types (validate-only) =="
owner="${REPO%%/*}"
# Keep the three failure modes apart. Swallowing stderr made an API refusal
# look identical to "every type is missing": the CI run reported all five types
# absent while they existed and were in use, and still concluded success.
err_file="$(mktemp)"
set +e
org_types="$(gh api "orgs/${owner}/issue-types" --jq '.[].name' 2>"$err_file")"
api_rc=$?
set -e
if [[ $api_rc -ne 0 ]]; then
  echo "  ::warning::could not read issue types for org ${owner} (exit ${api_rc}): $(tr '\n' ' ' <"$err_file" | cut -c1-200)"
  echo "  ::warning::the token needs org read access; validation SKIPPED, not passed"
  rm -f "$err_file"
elif [[ -z "$org_types" ]]; then
  rm -f "$err_file"
  echo "  ::warning::org ${owner} returned no issue types at all; validation SKIPPED, not passed"
else
  rm -f "$err_file"
  py '
import sys, yaml
for t in yaml.safe_load(open(sys.argv[1])).get("issue_types", []) or []:
    print(t["name"])
' | while read -r t; do
    if grep -qxF "$t" <<<"$org_types"; then
      echo "  ok: $t"
    else
      echo "  ::warning::issue type missing on org ${owner}: $t"
    fi
  done
fi

# ----- Project fields (validate-only) -------------------------------------
echo "== Project fields (validate-only) =="
pnum="$(py 'import sys,yaml; print((yaml.safe_load(open(sys.argv[1])).get("project") or {}).get("number",""))')"
if [[ -n "$pnum" ]]; then
  if fields="$(gh project field-list "$pnum" --owner "$owner" --format json --jq '.fields[].name' 2>/dev/null)"; then
    py '
import sys, yaml
for f in ((yaml.safe_load(open(sys.argv[1])).get("project") or {}).get("fields") or []):
    print(f["name"])
' | while read -r f; do
      if grep -qxF "$f" <<<"$fields"; then
        echo "  ok: $f"
      else
        echo "  ::warning::project #${pnum} missing field: $f"
      fi
    done
  else
    echo "  ::warning::could not read project #${pnum} fields (needs project scope); skipping validation"
  fi
fi

echo "Done."
