# Contributing to Astrocyte

Thank you for your interest in contributing to Astrocyte! This document provides guidelines and information for contributors.

## Code of Conduct

This project follows a code of conduct to ensure a welcoming environment for all contributors. Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## How to Contribute

### Development Setup

1. **Prerequisites**
   - Python 3.12+
   - Docker and Docker Compose
   - Git

2. **Clone and Setup**
   ```bash
   git clone https://github.com/astrocyte-project/astrocyte.git
   cd astrocyte
   make install   # uv sync + npm ci + pre-commit install
   ```

   See [docs/development.md](docs/development.md) for the full development
   guide, the CI jobs, and a troubleshooting reference. `uv` manages the
   Python 3.12 interpreter for you — no system Python 3.12 is required.

3. **Development Workflow**
   ```bash
   # Create a feature branch
   git checkout -b feat/your-feature-name

   # Make your changes
   # Run tests
   # Commit with conventional commit format
   git commit -m "feat: add amazing feature"

   # Push and create PR
   git push origin feat/your-feature-name
   ```

### Branch Naming Conventions

- `feat/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `chore/` - Maintenance tasks
- `refactor/` - Code refactoring
- `test/` - Testing related changes

### Commit Message Format

We use [Conventional Commits](https://conventionalcommits.org/) format:

```
type(scope): description

[optional body]

[optional footer]
```

Examples:
- `feat: add user authentication`
- `fix(api): resolve memory leak in health checks`
- `docs: update installation guide`

### Pull Request Process

1. **Create a PR** from your feature branch to `main`
2. **PR Title** should follow conventional commit format
3. **PR Description** should include:
   - What changes were made
   - Why the changes were needed
   - How to test the changes
   - Any breaking changes
4. **CI Checks** must pass
5. **Code Review** is required
6. **Squash Merge** is preferred

### Code Style

- **Python**: linted and formatted with [ruff](https://docs.astral.sh/ruff/)
  (line length 88), type-checked with mypy (strict). Run `make fmt`.
- **TypeScript/JavaScript**: ESLint + Prettier (`cd web && npm run lint`).
- **Documentation**: Use Markdown with consistent formatting.

Run `make check` before pushing — it mirrors the CI gates. Pre-commit hooks
(`pre-commit install`, included in `make install`) run the same checks on every
commit. **All CI checks must pass** before a PR can merge to `main`.

### Testing

- Write unit tests for new features
- Ensure all existing tests pass
- Test both happy path and error scenarios
- Include integration tests where appropriate

### Documentation

- Update documentation for any user-facing changes
- Include docstrings for Python functions
- Keep README.md up to date

## Issues, labels & triage

Astrocyte uses a GitHub-native project-management model — see
[docs/project-management.md](docs/project-management.md) for the full picture
(issue types, labels, milestones, and the board).

**Filing an issue:** pick the template that matches the *kind* of work —
Epic, Feature, Task, Spike, or Bug. The template sets the issue type; blank
issues are disabled.

<a name="issue-triage-checklist"></a>
**Issue triage checklist** — a triaged issue has:

- [ ] an **issue type** (Epic/Feature/Task/Spike/Bug);
- [ ] a **milestone** (v0.2–v1.0) — or the `backlog` label if unscheduled;
- [ ] one or more **`component:*`** labels (auto-applied on PRs by the labeler);
- [ ] a **`phase-*`** label if it maps to a roadmap phase;
- [ ] a link to its **parent Epic** as a sub-issue, where relevant;
- [ ] been added to the **[Astrocyte 1.0 board](https://github.com/orgs/astrocyte-project/projects/11)**, with **Effort** (High/Medium/Low) set once it enters active planning.

The full label taxonomy is in [`.github/labels.md`](.github/labels.md).

## Architecture Decisions

For significant changes, please document architectural decisions using Architecture Decision Records (ADRs). Create a new ADR in [`docs/adr/`](docs/adr/) following the [template](docs/adr/template.md). See [ADR-009](docs/adr/ADR-009-project-management.md) for how project management itself is run.

## Security

- Report security vulnerabilities via [SECURITY.md](SECURITY.md)
- Do not commit sensitive information
- Use secure coding practices

## Getting Help

- **Issues**: Use GitHub issues for bugs and feature requests
- **Discussions**: Use GitHub discussions for questions and general discussion
- **Documentation**: Check the [docs/](docs/) directory

## Recognition

Contributors are recognized in our release notes and on our website. Thank you for helping make Astrocyte better!
