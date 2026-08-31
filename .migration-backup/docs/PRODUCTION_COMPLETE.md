# ArveX Hosting SaaS — Production Completion Blueprint

This repository is designed as a secure control plane for Discord-driven Docker VPS and Pterodactyl game hosting. Production deployments MUST keep provider credentials and secrets outside Git.

## Production components

- Discord bot using Components V2
- FastAPI control plane
- PostgreSQL as the source of truth
- Redis-backed job/locking layer
- Deployment workers
- Docker node agents (least privilege; never expose the Docker socket to customer workloads)
- Pterodactyl application API integration
- Invite/reward engine with transactional redemption
- Multi-guild configuration isolation
- Admin control center with RBAC and audit logging
- Groq AI assistant using an allow-listed tool layer
- Monitoring, health checks, retries and idempotent provisioning
- Encrypted credentials at rest

## SSH / SSHX security model

The control plane must never expose a host shell to Discord users. SSH credentials are delivered only over an authenticated private channel, and access should be short-lived where possible. An SSHX-style collaborative terminal can be integrated through a separately deployed gateway that supports authentication, expiry, revocation and audit logging. Do not assume a third-party hosted relay is self-hostable or trustworthy; keep the gateway replaceable behind an interface.

## Provisioning invariants

1. Validate plan limits server-side; never trust Discord/client values.
2. Reserve invite balance in a PostgreSQL transaction before creating resources.
3. Create an idempotent deployment job with a unique request key.
4. Select only healthy, enabled, non-draining nodes with sufficient capacity.
5. Apply memory, CPU, PID, disk and network policy at the node boundary.
6. Store only encrypted credentials; never log secrets.
7. On failure, retry only safe/idempotent stages and compensate the invite reservation exactly once.
8. Every state transition is auditable.
9. Customer containers never receive privileged mode, host filesystem mounts, or the Docker socket.
10. Destructive actions require explicit authorization and confirmation.

## Pterodactyl

Use a dedicated least-privilege application API key. Treat allocations, nodes, eggs and server limits as server-side configuration. Never expose Pterodactyl API keys to Discord clients or frontend JavaScript.

## AI safety

Groq is an assistant, not an authority. AI may read approved platform data and propose actions. Any operation that changes infrastructure, spends credits, deletes data, rotates credentials, or changes permissions must pass explicit backend authorization and confirmation. Never allow arbitrary shell execution through the AI tool interface.

## Required production checks

- Run the complete CI suite before deployment.
- Run database migrations before workers are enabled.
- Configure HTTPS, HSTS and a real secret manager/environment injection.
- Configure PostgreSQL backups and test restores.
- Configure Redis persistence/HA appropriate to the deployment.
- Monitor API, bot, workers, nodes and Pterodactyl.
- Alert on repeated deployment failures, node capacity exhaustion and authentication failures.
- Rotate all development credentials before production.
- Keep Docker, OS, Python dependencies and Pterodactyl patched.
- Use a private management network for node-agent traffic.

## Definition of done

A feature is considered production-ready only after implementation, automated tests, failure-path tests, authorization tests, and deployment documentation exist. UI completion alone is not sufficient.
