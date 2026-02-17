# Splitting high-risk refactors into scoped PRs

Goal: reduce blast radius and make rollbacks simple by separating concerns.

## Recommended split

### PR 1 — Branding (low risk)

Includes:
- Copy changes, onboarding text, marketing/landing content
- Static assets (logos/icons)
- Documentation
- Frontend-only styling changes

Avoid:
- Settings/env var behavior changes
- Docker, entrypoint, web server bindings
- Auth/session changes

### PR 2 — Runtime config / deploy behavior (higher risk)

Includes:
- Django settings changes (env vars, security flags)
- Dockerfile / entrypoint / process manager changes
- GitHub Actions deploy config
- CapRover/app runtime configuration changes

Avoid:
- Simultaneous branding/copy churn (harder to review)

## Operational guidelines

- Each PR should include:
  - a clear rollback note ("revert PR X")
  - a deploy note if anything changes in runtime/deploy
- Prefer feature flags for risky runtime behavior.
- For migrations/backfills:
  - ship schema changes first
  - deploy code that tolerates old+new schema
  - backfill async
  - only then remove old fields/paths
