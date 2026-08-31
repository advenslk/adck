# ArveX Hosting SaaS Security Model

## Trust boundaries
- Discord bot is an untrusted client of the API and authenticates requests with an HMAC signature containing method, path, timestamp, Discord user ID and body hash.
- The API never receives a Docker socket. Infrastructure operations belong to the worker/provider boundary.
- Dashboard authentication uses a server-side bearer token. Never put this token in `NEXT_PUBLIC_*` variables.
- Provider credentials are server-side environment secrets only.

## Infrastructure rules
- Customer containers must never be privileged.
- Do not mount `/var/run/docker.sock` into customer containers.
- Use an allow-list for customer images and enforce RAM/CPU/disk/PID limits.
- Use dedicated networks and persistent per-server storage.
- Keep host SSH management separate from customer SSH.
- Do not expose provider API keys, database URLs, internal secrets or credential-encryption keys to Discord messages or browser JavaScript.

## Credentials
- Generated VPS passwords are encrypted at rest with the configured Fernet key.
- Passwords should only be revealed to the owning user through a private channel/DM and should never be written to audit logs.
- Rotate Discord, Pterodactyl, Groq, database and internal secrets after any suspected exposure.

## AI safety
- Groq is an assistant, not an infrastructure shell.
- AI tools must be allow-listed and scoped to the requesting user's resources.
- Destructive operations require application-side authorization and explicit confirmation.
- Never give the model raw SQL, Docker socket access, host shell access, secrets or arbitrary URLs to fetch.

## Production checklist
1. Set `ENVIRONMENT=production`.
2. Use a long random `INTERNAL_API_SECRET`, `ADMIN_DASHBOARD_TOKEN` and `CREDENTIAL_ENCRYPTION_KEY`.
3. Set `TRUSTED_HOSTS` to exact production hostnames.
4. Set `CORS_ORIGINS` to the exact dashboard origin; do not use `*`.
5. Put API, dashboard and provider endpoints behind TLS.
6. Restrict PostgreSQL/Redis/Docker access to private networks.
7. Run the API and worker as separate non-root application processes.
8. Give the worker only the infrastructure permissions it needs.
9. Back up PostgreSQL and server metadata before production migrations.
10. Monitor failed deployments, node health, authentication failures and unusual invite activity.
