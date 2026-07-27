# Development Guide

How to set up Astrocyte locally, what CI enforces, and how to fix common
failures. The tooling decisions behind this are recorded in
[ADR-008](adr/ADR-008-dev-tooling-cicd.md).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages Python; it will fetch Python 3.12
  for you — no system Python 3.12 required)
- Node.js 24 (see `web/.nvmrc`)
- Docker / Docker Compose (Podman works via its Docker CLI shim)

## One-time setup

```bash
make install      # uv sync + npm ci + pre-commit install
```

This installs Python and web dependencies and the git pre-commit hooks.

## Everyday commands

All commands are defined in the [`Makefile`](../Makefile) so local and CI runs
never drift:

| Command          | What it does                                        |
| ---------------- | --------------------------------------------------- |
| `make check`     | Run all gates: lint + type-check + tests            |
| `make lint`      | ruff (Python) + ESLint/Prettier (web)               |
| `make typecheck` | mypy (strict) + `tsc --noEmit`                      |
| `make test`      | pytest (+coverage) + Vitest                         |
| `make fmt`       | Auto-format Python and web                          |
| `make build`     | Build the web bundle                                |
| `make docker-build` | Build the API image via compose                  |
| `make security`  | `pip-audit` + `npm audit`                           |

Run the API locally:

```bash
uv run uvicorn astrocyte.api.app:create_app --factory   # http://localhost:8000/health
uv run aios --version
```

Run the full stack in Docker:

```bash
docker compose up --build      # then: curl http://localhost:8000/health
```

Python extras (`rvc`, `ha`, `mcp`, `agents`) are always installed by
`make install` (`uv sync --all-extras`) and in CI — new subsystem code is not
optional at development time.

## RV subsystem specifics

- **SocketCAN is Linux-only** (by design — the bridge deploys to the coach
  Pi, ADR-012). Unit tests use python-can's in-process `virtual` bus, so
  `make test` passes on any OS.
- **vcan integration tests** (`pytest -m vcan`) need a `vcan0` interface and
  an MQTT broker; they auto-skip otherwise. Local setup (Linux):

  ```bash
  # Fedora needs the extra-modules package first:
  sudo dnf install kernel-modules-extra   # Ubuntu: linux-modules-extra-$(uname -r)
  sudo modprobe vcan
  sudo ip link add dev vcan0 type vcan && sudo ip link set up vcan0
  docker run -d -p 1883:1883 docker.io/library/eclipse-mosquitto:2 \
    mosquitto -c /mosquitto-no-auth.conf
  uv run pytest -m vcan --no-cov
  ```

- **The coach `sim` profile** (`deploy/coach/compose.yaml --profile sim`)
  runs the whole coach stack against a fixture replayer with no CAN hardware.
  It relies on host networking, so it is **Linux-only** (Docker Desktop on
  macOS/Windows can't do host networking). Compose bind mounts carry `:z`
  for SELinux hosts (Fedora).
- **Local arm64 image builds** (`docker buildx build --platform linux/arm64`)
  need QEMU binfmt handlers (`sudo dnf install qemu-user-static` on Fedora);
  CI covers this on every main push and release regardless.

## What CI enforces

`.github/workflows/ci.yml` runs on every PR and push to `main`:

| Job          | Enforces                                                        |
| ------------ | --------------------------------------------------------------- |
| `python-lint`| `ruff check`, `ruff format --check`, `mypy src`                 |
| `python-test`| `pytest` with coverage; posts a coverage comment to the PR      |
| `web-lint`   | ESLint, Prettier, `tsc`, Vitest, and `vite build` in `web/`     |
| `docker-build`| Builds the API image from a clean context                      |
| `security`   | `pip-audit`, `npm audit --audit-level=high`, Trivy image scan   |

Releases (`release.yml`) build and push images to GHCR and create a GitHub
Release when a `v*` tag is pushed.

Two more workflows support project management (see
[project-management.md](project-management.md)): `labeler.yml` auto-applies
`component:*` labels to PRs by path, and `project-sync.yml` reconciles labels,
milestones, and the board from `.github/project.yml`.

## Troubleshooting CI failures

Reproduce almost everything locally with `make check` (and `make security` /
`make docker-build`).

- **`ruff check` failed** — run `make fmt` to auto-fix, then re-run `make lint`.
  Some lint rules (e.g. `B`, `SIM`) need a manual code change.
- **`ruff format --check` failed** — run `uv run ruff format .` (or `make fmt`).
- **`mypy` failed** — add/repair type annotations; mypy runs in `strict` mode.
  If a third-party import lacks stubs, add the package to the pre-commit mypy
  hook's `additional_dependencies` too.
- **Coverage below the floor** — add tests, or temporarily lower
  `--cov-fail-under` in `pyproject.toml` only as part of a deliberate change.
- **`web-lint` failed** — `cd web && npm run lint`/`format`/`typecheck`/`test`
  reproduce each step; `npm run format` fixes formatting.
- **`security` failed** — `make security` shows the advisory. Prefer bumping the
  affected dependency (Dependabot usually has a PR open). Trivy uses
  `ignore-unfixed`, so failures are fixable CVEs in the image.
- **`docker-build` failed** — `make docker-build` reproduces it. The build needs
  `pyproject.toml`, `uv.lock`, `src/`, and `README.md` in context; check
  `.dockerignore` if a needed file is missing.
- **Lockfile out of date** (`uv sync --frozen` errors in CI) — run `uv lock` and
  commit the updated `uv.lock`.
