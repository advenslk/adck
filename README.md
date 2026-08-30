# ArveX Hosting SaaS

Discord-first hosting automation platform for invite rewards, Docker VPS provisioning, Pterodactyl game servers, Groq AI support, and an admin control plane.

## Architecture

- `apps/api` — FastAPI control plane and REST API
- `apps/api/dashboard.py` — token-authenticated admin plan management
- `apps/bot` — Discord Components V2 interaction layer
- `apps/worker` — locked/retryable provisioning worker
- `apps/web` — protected admin dashboard
- PostgreSQL — durable state
- Redis — queue/cache integration
- Docker — isolated VPS workloads
- Pterodactyl — game-server provisioning
- Groq — AI assistant

## Security model

- Discord-to-API user requests use timestamped HMAC signatures; a Discord ID header alone is never trusted.
- Signed requests include method, query string, path, user id and body hash to prevent tampering/replay.
- Admin web access uses a server-side bearer token entered at login; no admin identity is shipped in `NEXT_PUBLIC_*` variables.
- VPS credentials are encrypted at rest with Fernet and are excluded from normal server-list responses.
- VPS images are allow-listed and resource limits are enforced before provisioning.
- Customer containers never receive the Docker socket, privileged mode, or unrestricted host mounts.
- The worker does not receive the raw Docker socket; Docker API access is routed through a restricted socket proxy with exec, volumes, swarm, events and system APIs disabled.
- Docker VPS containers drop all capabilities except the minimum required for the SSH daemon and use `no-new-privileges`.
- API security headers, trusted-host validation and rate limiting are included in the security layer.
- Invite redemption uses row locking so concurrent requests cannot double-spend the same invite balance.
- Deployment jobs are locked with `SKIP LOCKED`, retried with a maximum attempt count, and stale worker jobs are recoverable.
- AI is designed around allow-listed application tools; it must never receive arbitrary shell/Docker access. Groq local tool calling keeps tool execution under application control.

## Quick start

1. Copy `.env.example` to `.env`.
2. Generate strong values for `POSTGRES_PASSWORD`, `INTERNAL_API_SECRET`, `ADMIN_DASHBOARD_TOKEN`, and `CREDENTIAL_ENCRYPTION_KEY`.
3. Set `VPS_PUBLIC_HOST` to the public address of the Docker node.
4. Configure your Discord bot and Pterodactyl credentials.
5. Start the stack with `docker compose up -d --build`.
6. Put Nginx/Cloudflare in front of the web/API services and use HTTPS in production.
7. Open the admin web app and enter the `ADMIN_DASHBOARD_TOKEN`.

## Validation

CI runs Python compilation and security-focused pytest checks on pushes and pull requests.

## Production checklist

Before exposing the platform publicly, set production secrets, use a dedicated Docker node/worker host, restrict firewall access, terminate TLS at the reverse proxy, configure trusted hosts/CORS for the real domains, rotate provider credentials regularly, enable database backups, and configure a real SSHX gateway if SSHX links are required.

The repository is intentionally provider-configurable: provider credentials, node addresses, Pterodactyl eggs/locations, and the SSHX gateway are deployment configuration rather than hardcoded secrets.
