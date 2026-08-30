# ArveX Hosting SaaS

Discord-first hosting automation platform for invite rewards, Docker VPS provisioning, Pterodactyl game servers, Groq AI support, and an admin control plane.

## Architecture

- `apps/api` — FastAPI control plane and REST API
- `apps/bot` — Discord bot using Components V2-style interaction architecture
- `apps/worker` — background provisioning worker
- `apps/web` — admin dashboard starter
- PostgreSQL — durable state
- Redis — queues/cache/locks
- Docker — isolated VPS workloads
- Pterodactyl — game-server provisioning
- Groq — AI assistant with local tool calling

## Safety model

The AI never receives direct Docker shell access. It can only request allow-listed application tools. Destructive actions require explicit authorization/confirmation.

Customer containers are never given `/var/run/docker.sock`, privileged mode, or unrestricted host mounts.

## Quick start

1. Copy `.env.example` to `.env` and fill secrets.
2. Run `docker compose up -d postgres redis`.
3. Install Python dependencies with `pip install -e .`.
4. Start API: `uvicorn apps.api.main:app --reload`.
5. Start bot: `python -m apps.bot`.
6. Start worker: `python -m apps.worker`.

See `.env.example` for configuration.

## Current milestone

This repository starts with a production-oriented foundation: database models, plan/invite APIs, provisioning abstractions, Groq tool-calling service, Discord interaction layer, worker queue, audit logging, and a dashboard shell. Provider-specific credentials and node configuration remain environment/deployment concerns.
