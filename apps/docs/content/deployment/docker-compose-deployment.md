---
title: Docker Compose
description: Deploy Clawrn on your own server using Docker Compose.
keywords: Clawrn, deployment, docker compose, self-hosting
author: Forge
---

Use this when you want a simple self-hosted setup on a VPS.

## Prerequisites

- Docker + Docker Compose installed
- SSH access to your server
- A domain (recommended)

## 1) Create a deployment folder

```bash
mkdir clawrn-deployment
cd clawrn-deployment
```

## 2) Download config files

```bash
curl -o .env https://github.com/gregagi/clawrn/raw/main/.env.example
curl -o docker-compose-prod.yml https://github.com/gregagi/clawrn/raw/main/docker-compose-prod.yml
```

## 3) Configure `.env`

At minimum, set:
- `ENVIRONMENT=prod`
- `DEBUG=off`
- `SECRET_KEY`
- `SITE_URL`
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`

See [Environment Variables](/docs/deployment/environment-variables/) for details.

## 4) Start the stack

```bash
docker-compose -f docker-compose-prod.yml -p "clawrn" up --detach --remove-orphans
```

This starts:
- postgres
- redis
- web (Django)
- workers

## 5) Verify

```bash
docker-compose -f docker-compose-prod.yml -p "clawrn" ps
curl -sS https://your-domain.com/api/healthcheck
```

Expected health response:

```json
{"status":"healthy","checks":{"database":"healthy","redis":"healthy"}}
```

## Expose with Nginx (recommended)

Route your domain to the web container on port `8000` and enable HTTPS with Certbot.

Minimal upstream:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## Troubleshooting

- App boots but tasks fail → check Redis host/password.
- 500 on startup → check Postgres credentials and migrations.
- Static issues → run collectstatic in your deploy path/process.
