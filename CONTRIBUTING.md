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

## Releasing

Releases are triggered by version bumps, not manual tagging:

1. In one PR: bump `version` in `pyproject.toml`, and rename `CHANGELOG.md`'s
   `[Unreleased]` section to `## [x.y.z] - YYYY-MM-DD` (add a fresh empty
   `[Unreleased]` above it for the next round of changes).
2. Once that PR merges to `main` and CI passes, `.github/workflows/release.yml`
   automatically tags the commit `vX.Y.Z`, creates a GitHub Release (body taken
   from that version's `CHANGELOG.md` section), which in turn triggers
   `.github/workflows/publish.yml` to build and publish to PyPI via Trusted
   Publishing.
3. If `pyproject.toml`'s version isn't bumped, nothing is released — merging
   unrelated changes to `main` is safe and won't trigger a release.
