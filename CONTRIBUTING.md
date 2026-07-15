# Contributing

## Development setup

```bash
uv sync --all-groups
```

## Running checks locally

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest --cov=ebms_adapter_client
```

All four must pass before opening a pull request; CI runs the same checks across the
supported Python version matrix (see `.github/workflows/ci.yml`).

## Pull requests

- Keep changes focused and add/update tests for any behavioral change.
- Update `CHANGELOG.md` under `[Unreleased]` for user-visible changes.
- This package intentionally has no NotifyNL-specific code — keep it a
  standalone client for `ebms-core`'s REST API and the Berichtenbox XML format.
