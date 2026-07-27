#!/usr/bin/env bash
#
# triage-backlog.sh — one-shot (idempotent) triage of the open backlog.
#
# For each issue in the map below it sets the issue type, milestone, and
# component labels, adds it to the "Astrocyte 1.0" board (#11), and links it as a
# sub-issue of the MVP Epic (#2). Safe to re-run: type/milestone/label edits are
# idempotent, and board/sub-issue adds tolerate "already exists".
#
# Prereqs: labels + milestones must already exist (run scripts/project-sync.sh
# first), and a `gh` session with repo + project + org scopes.
#
# Usage: bash scripts/triage-backlog.sh

set -euo pipefail

REPO="astrocyte-project/astrocyte"
OWNER="astrocyte-project"
PROJECT=11
EPIC=2

M02="v0.2 — Foundation & DX"
M03="v0.3 — Ops Agent & curated apps"
M04="v0.4 — RAG layer & unified search"
M10="v1.0 — Atomic backup & polish"

# num | type | milestone | comma-separated component/meta labels
# (Every issue except the Epic itself is linked as a sub-issue of #2.)
MAP=$(cat <<EOF
2|Epic||epic,architecture,component:core
6|Feature|$M02|component:agent,component:docs
7|Feature|$M03|component:agent
8|Feature|$M03|component:agent
9|Feature|$M03|component:cli
10|Feature|$M03|component:core
11|Feature|$M03|component:network
12|Feature|$M03|component:network
13|Feature|$M03|component:agent
14|Feature|$M03|component:web
15|Feature|$M03|component:mcp,component:agent
16|Feature|$M04|component:rag
17|Feature|$M04|component:rag,component:agent
18|Feature|$M04|component:rag,component:api
19|Feature|$M04|component:rag
20|Feature|$M04|component:rag
21|Feature|$M04|component:rag,component:agent
22|Feature|$M04|component:web
23|Feature|$M04|component:mcp,component:rag
24|Feature|$M10|component:backup
25|Feature|$M10|component:backup
26|Feature|$M10|component:backup
27|Feature|$M10|component:backup
28|Feature|$M10|component:backup
29|Feature|$M10|component:backup,component:agent
30|Feature|$M10|component:web
31|Feature|$M10|component:mcp,component:backup
32|Task|$M02|component:devx,component:docs
33|Feature|$M02|component:devx
34|Feature|$M02|component:devx,component:docs
39|Task|$M02|component:ci
40|Task|$M02|component:ci
41|Task|$M02|component:ci
EOF
)

# Node id of the Epic, for sub-issue linking.
epic_id=$(gh issue view "$EPIC" --repo "$REPO" --json id --jq .id)

while IFS='|' read -r num type ms labels; do
  [[ -z "$num" ]] && continue
  echo "== #$num ($type) =="

  # Type + labels (+ milestone unless empty).
  args=(--repo "$REPO" --type "$type" --add-label "$labels")
  if [[ -n "$ms" ]]; then
    args+=(--milestone "$ms")
  fi
  gh issue edit "$num" "${args[@]}" >/dev/null
  echo "  set type/labels${ms:+/milestone}"

  # Add to the board (idempotent — ignore "already exists").
  url="https://github.com/$REPO/issues/$num"
  if gh project item-add "$PROJECT" --owner "$OWNER" --url "$url" >/dev/null 2>&1; then
    echo "  added to board #$PROJECT"
  else
    echo "  board: already present (or add skipped)"
  fi

  # Link as sub-issue of the Epic (skip the Epic itself).
  if [[ "$num" != "$EPIC" ]]; then
    child_id=$(gh issue view "$num" --repo "$REPO" --json id --jq .id)
    if gh api graphql -f query='
      mutation($parent:ID!,$child:ID!){
        addSubIssue(input:{issueId:$parent, subIssueId:$child}){ issue { number } }
      }' -f parent="$epic_id" -f child="$child_id" >/dev/null 2>&1; then
      echo "  linked as sub-issue of #$EPIC"
    else
      echo "  sub-issue: already linked (or link skipped)"
    fi
  fi
done <<<"$MAP"

echo "Triage complete."
