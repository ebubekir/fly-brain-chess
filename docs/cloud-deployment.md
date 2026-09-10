# Cloud deployment

This service is WebSocket-heavy and keeps active games in backend memory. Treat
it as a single-instance application until shared session ownership is added.

## Provider-neutral VM

Use a Linux VM with Docker Engine, a DNS record, and a TLS reverse proxy such as
Caddy, Traefik, or Nginx. Keep Compose bound to `127.0.0.1:8000:8080`, terminate
TLS at the proxy, and proxy both HTTP and WebSocket traffic to that port. Set:

```dotenv
ALLOWED_ORIGINS=https://chess.example.com
MAX_SESSIONS=128
SESSION_TTL_SECONDS=3600
```

Deploy with `docker compose up --build -d`, check `docker compose ps`, and probe
`/api/health`. Configure a WebSocket read timeout of at least 100 seconds. Never
publish port 8001. Use a firewall to allow only SSH (restricted), HTTPS, and
any required monitoring endpoint.

## Managed containers

Deploy both Compose services in one task/pod, or place the backend behind a
sticky-session capable load balancer. The frontend must reach `/api` and `/ws`
through the same public origin. Configure the backend health check as
`GET /api/health`; reserve 512 MiB memory and 2 vCPUs. Build images in CI and
pin the resulting digest in your release process.

AWS ECS, Google Cloud Run, and Azure Container Apps can host the containers, but
their defaults vary: explicitly enable WebSocket upgrades, increase request
timeouts, and disable scale-to-zero while a game is in progress if your product
requires uninterrupted trials. Keep one backend replica until Redis or another
shared session/queue layer is implemented.

## Data and security

FlyWire FAFB v783 data and the readout are read-only image assets. They do not
need runtime credentials. The public FlyWire release is CC BY-NC 4.0; preserve
the provenance and citation in `backend/data/flywire_783.json` and comply with
that license for commercial deployments. Do not commit raw bulk downloads from
`data/raw/`.

The `sessionStorage` token is a bearer capability for one game. TLS protects it
in transit; never place it in analytics, access logs, or URLs shared publicly.
The included Nginx config redacts `/ws` access logs. Add an identity gateway,
rate limiting, centralized logs, and alerting before exposing the app publicly.

## Scaling path

The current backend deliberately runs one Uvicorn worker and stores sessions in
RAM. A production multi-replica design needs a shared session store, a lease for
one active socket per session, a durable simulation job queue, and a way to
stream results to reconnecting clients. Preserve the reservoir fingerprint and
readout checkpoint hash when moving inference to workers.
