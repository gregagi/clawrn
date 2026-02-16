---
title: Environment Variables
description: Required and optional environment variables for Clawrn deployments.
keywords: Clawrn, environment variables, configuration
author: Forge
---

This page covers the env vars you need for a stable Clawrn deployment.

## Required

### Runtime

- `ENVIRONMENT` — `dev` or `prod`
- `DEBUG` — `off` in production
- `SECRET_KEY` — Django secret
- `SITE_URL` — full public URL (for links/emails)

### Postgres

- `POSTGRES_HOST`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT` (default `5432`)

### Redis

- `REDIS_HOST`
- `REDIS_PASSWORD`
- `REDIS_PORT` (default `6379`)
- `REDIS_DB` (default `0`)

## Common optional

- `OPENAI_API_KEY` — if your flows use OpenAI models
- `MAILGUN_API_KEY` — transactional email backend
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` — GitHub social login
- `SENTRY_DSN` — error tracking
- `LOGFIRE_TOKEN` — telemetry
- `DJANGO_LOG_LEVEL` — logging level in production

## Production defaults to enforce

- `DEBUG=off`
- strong random values for `SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`
- `SITE_URL=https://clawrn.com` (or your actual domain)

## Security checklist

- Never commit `.env` to git.
- Rotate secrets if leaked.
- Restrict DB/Redis network exposure.
- Use HTTPS in front of the app.

## Download starter env file

```bash
curl -o .env https://github.com/gregagi/clawrn/raw/main/.env.example
```
