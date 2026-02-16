---
title: Deploying Clawrn to Render
description: Deploy Clawrn on Render using the repository blueprint.
keywords: Clawrn, deployment, render
author: Forge
---

Use this path if you want fast managed hosting without maintaining servers.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/gregagi/clawrn)

## What gets provisioned

The Render blueprint creates:
- web service
- worker service
- Redis
- Postgres

## Before you deploy

Review and set required env vars in Render:
- `ENVIRONMENT=prod`
- `DEBUG=off`
- `SECRET_KEY`
- `SITE_URL`
- DB/Redis credentials if overriding generated values

See [Environment Variables](/docs/deployment/environment-variables/).

## Verify after deploy

1. Open the app URL and confirm homepage loads.
2. Check health endpoint:

```bash
curl -sS https://YOUR_RENDER_DOMAIN/api/healthcheck
```

Expected:

```json
{"status":"healthy","checks":{"database":"healthy","redis":"healthy"}}
```

3. Confirm worker service is running and not crash-looping.

## Notes

- Render free tiers may sleep and have resource limits.
- For consistent background processing, paid worker plans are recommended.
