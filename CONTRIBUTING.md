# Contributing to AI Agent

Thank you for taking the time to contribute! 🎉  
This document covers how to report issues, propose features, and submit code.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [How to Contribute](#how-to-contribute)
4. [Development Workflow](#development-workflow)
5. [Commit Message Convention](#commit-message-convention)
6. [Pull Request Checklist](#pull-request-checklist)
7. [Coding Standards](#coding-standards)
8. [Testing](#testing)
9. [Security Disclosures](#security-disclosures)

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
By participating, you agree to uphold it.

---

## Getting Started

```bash
# 1. Fork the repository on GitHub
# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/ai-agent.git
cd ai-agent

# 3. Set up the upstream remote
git remote add upstream https://github.com/OWNER/ai-agent.git

# 4. Create a virtual environment and install dev dependencies
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 5. Copy the env template and fill in your values
cp .env.example .env
```

---

## How to Contribute

### Reporting Bugs

- Search [existing issues](../../issues) first to avoid duplicates.
- Use the **Bug Report** issue template.
- Include: Python version, steps to reproduce, expected vs actual behaviour,
  and relevant log output.

### Proposing Features

- Open a [Feature Request](../../issues/new?template=feature_request.yml).
- Describe the problem it solves, not just the solution.
- Discuss the proposal before spending time on a large implementation.

### Improving Documentation

Documentation lives alongside the code. Open a PR with improvements to
`README.md`, docstrings, or files in `docs/`.

---

## Development Workflow

```bash
# Always branch off main
git fetch upstream
git checkout main
git merge upstream/main

# Create a descriptive branch
git checkout -b feat/add-weather-tool   # or fix/session-ttl-bug

# Make your changes, then run the full test suite
pytest --cov=app --cov-report=term-missing

# Lint and format
ruff check app/ tests/
ruff format app/ tests/

# Commit using Conventional Commits (see below)
git add -p          # stage changes interactively (atomic commits)
git commit -m "feat(tools): add weather_current tool"

# Push and open a PR
git push origin feat/add-weather-tool
```

---

## Commit Message Convention

This project follows **[Conventional Commits](https://www.conventionalcommits.org/)**.

```
<type>(<scope>): <short summary>

[optional body]

[optional footer(s)]
```

### Types

| Type       | When to use                                        |
|------------|----------------------------------------------------|
| `feat`     | A new feature                                      |
| `fix`      | A bug fix                                          |
| `docs`     | Documentation only                                 |
| `style`    | Formatting, whitespace (no logic change)           |
| `refactor` | Code restructuring (no feature/fix)                |
| `perf`     | Performance improvement                            |
| `test`     | Adding or updating tests                           |
| `build`    | Build system, dependencies, Docker                 |
| `ci`       | CI/CD configuration                                |
| `chore`    | Maintenance tasks; no production code change       |
| `security` | Security hardening or vulnerability fix            |
| `revert`   | Reverting a previous commit                        |

### Examples

```
feat(tools): add weather_current tool with OpenWeatherMap integration
fix(memory): prevent Redis key collision across sessions
docs(readme): add deployment troubleshooting section
ci(github-actions): pin action versions to SHA hashes
security(http_request): add scheme allowlist (https only)
```

### Breaking Changes

Append `!` after the type/scope and include a `BREAKING CHANGE:` footer:

```
feat(api)!: rename /chat to /v2/chat

BREAKING CHANGE: The /api/v1/chat endpoint is removed. Use /api/v2/chat.
```

---

## Pull Request Checklist

Before requesting a review, ensure:

- [ ] My branch is up to date with `upstream/main`
- [ ] All tests pass: `pytest -q`
- [ ] Lint passes: `ruff check app/ tests/`
- [ ] Format passes: `ruff format --check app/ tests/`
- [ ] New code is covered by tests (aim for > 80% on changed files)
- [ ] I have not committed secrets, `.env` files, or build artefacts
- [ ] I have updated `README.md` / docstrings if the public interface changed
- [ ] The PR description references a related issue (`Closes #123`)

---

## Coding Standards

- **Python 3.12+** — use modern syntax (`match`, `|` unions, `zoneinfo`).
- **Type hints** — annotate all public functions and methods.
- **Docstrings** — use Google-style for public functions.
- **Async** — all I/O must be `async`. Never use blocking calls on the
  event loop (no `time.sleep`, no synchronous `requests`).
- **Pydantic v2** — use `model_validator` / `field_validator`, not `validator`.
- **No bare `except:`** — catch specific exceptions.
- **Secrets** — never hardcode. Always read from `get_settings()`.

### Adding a New Tool

1. Create `app/tools/<tool_name>.py` with an `async def <tool_name>(**kwargs)`.
2. Add the JSON schema to `TOOLS_SCHEMAS` in `app/tools/registry.py`.
3. Register the handler in `_HANDLERS`.
4. Add input validation in `_TOOL_VALIDATORS` if applicable.
5. Write unit tests in `tests/unit/test_tools.py`.

---

## Testing

```bash
# All tests
pytest

# Unit tests only (no network required)
pytest tests/unit/ -v

# Integration tests (mocked OpenAI API)
pytest tests/integration/ -v

# With coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

Tests use `pytest-asyncio` in `asyncio_mode = "auto"`. All async test
functions are discovered automatically.

---

## Security Disclosures

Do **not** open a public issue for security vulnerabilities.  
Follow the process in [SECURITY.md](SECURITY.md).

---

## Questions?

Open a [Discussion](../../discussions) or ask in the relevant issue thread.
We aim to respond within 2 business days.
