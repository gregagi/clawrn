# Release checklist (Clawrn)

This checklist is for shipping changes safely with minimal blast radius and clear rollback.

## Before you start

- Confirm the Todoist task / scope is clear.
- Prefer multiple small PRs over one large refactor.
- If a change affects prod data (migrations, backfills), get explicit approval before shipping.

## PR hygiene

- Keep PRs scoped:
  - **Branding-only** changes: copy, UI strings, logos/assets, documentation.
  - **Runtime config / deploy** changes: environment variables, settings, Docker/entrypoints, CapRover/GitHub Actions config.
  - Avoid mixing the two unless unavoidable.
- Link the originating task in the PR title or body.
- Update `CHANGELOG.md` under **Unreleased**.

## Local verification

- Install deps: `uv sync`
- Run tests: `uv run pytest`
- Run formatting/linting if applicable (see `Makefile` / repo docs).
- If frontend changed:
  - Ensure Tailwind build works.
  - Smoke-check key pages.

## Deployment readiness

- Confirm no secrets are committed.
- Confirm env var changes are documented:
  - Add to `docs/` or deployment docs as appropriate.
  - Ensure defaults are safe.
- Confirm database migrations are safe:
  - Migrations are reversible when feasible.
  - Large tables: avoid lock-heavy operations.

## Merge + deploy

- Wait for GitHub Actions to complete.
- Merge only when checks are green.
- Verify deploy workflow ran (or trigger it if manual).

## Post-deploy smoke checks

- Basic health:
  - Home page loads
  - Auth/login flow
  - Key API endpoints used by agents
- Background jobs/workers (if applicable) are running.
- Error monitoring: check for new spikes.

## Rollback plan

- If a release breaks production:
  - Revert the PR (preferred) or roll back to the last known-good image.
  - If migrations were applied, assess reversibility before rolling back code.
