# Branch Protection for `main`

`main` is protected by a repository **ruleset** (`main`, id `18257584`), not
classic branch protection. Rulesets require repository admin rights and cannot be
created from a pull request — a maintainer applies/updates them once. This
satisfies the branch-protection acceptance item of #5 (#39).

## What we enforce

- **Pull request required** to merge — direct pushes to `main` are blocked.
- **All CI checks must pass** before merge (strict / up to date with `main`):
  `Python lint & type check`, `Python tests & coverage`,
  `Web lint, type check, test & build`, `Docker build`, `Security scan`.
- **Conversations must be resolved** before merge.
- **Linear history**, **squash-only** merges (matches CONTRIBUTING.md), and
  branch **auto-delete** on merge.
- Force-pushes and branch deletion are blocked.

### Deferred while the project is solo-maintained

Review requirements are intentionally **off** for now, because GitHub does not
let an author approve their own PR — requiring either would lock the sole
maintainer out of merging:

- `required_approving_review_count` = **0** (target: 1)
- code-owner review = **off** (target: on, see [CODEOWNERS](CODEOWNERS))

When a second maintainer joins, re-enable both on ruleset `18257584` (see below).

## Apply / update with the GitHub CLI

Run as a repo admin (`gh auth status` to check). Fetch the current ruleset,
edit the `pull_request` and `required_status_checks` rules, and PUT it back:

```bash
# Inspect the current ruleset
gh api repos/astrocyte-project/astrocyte/rulesets/18257584

# Update it (edit the JSON body first — see the rules array)
gh api -X PUT repos/astrocyte-project/astrocyte/rulesets/18257584 --input ruleset.json
```

The `rules` array we apply (solo configuration):

```json
[
  { "type": "deletion" },
  { "type": "non_fast_forward" },
  { "type": "required_linear_history" },
  { "type": "pull_request", "parameters": {
      "required_approving_review_count": 0,
      "require_code_owner_review": false,
      "dismiss_stale_reviews_on_push": true,
      "require_last_push_approval": false,
      "required_review_thread_resolution": true,
      "allowed_merge_methods": ["squash"]
  } },
  { "type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "do_not_enforce_on_create": false,
      "required_status_checks": [
        { "context": "Python lint & type check" },
        { "context": "Python tests & coverage" },
        { "context": "Web lint, type check, test & build" },
        { "context": "Docker build" },
        { "context": "Security scan" }
      ]
  } }
]
```

> To require reviews once there are more maintainers, set
> `required_approving_review_count` to `1` and `require_code_owner_review` to
> `true`.

Repository merge settings (squash-only + auto-delete) are enforced separately:

```bash
gh api -X PATCH repos/astrocyte-project/astrocyte \
  -F allow_squash_merge=true \
  -F allow_merge_commit=false \
  -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true
```

> The `context` values are the **job names** from
> [`workflows/ci.yml`](workflows/ci.yml). If you rename a job, update it here and
> in the ruleset.
