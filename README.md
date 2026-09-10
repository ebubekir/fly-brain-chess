# Fly Brain / Chess

**Your move. Its neurons.**

Play chess against a spiking neural network whose frozen reservoir is induced
from a real FlyWire FAFB v783 subgraph. Watch sensory impulses
spread through a glowing 3D graph, then resolve into a legal move. Everything
runs on your machine. No API keys. No cloud inference. No Stockfish hiding inside.

## Fire it up

Install Docker Engine with Compose or Docker Desktop, then from this directory:

```sh
docker-compose up --build
```

Modern Compose uses the equivalent `docker compose up --build`.
Open **[localhost:8000](http://localhost:8000)** when the containers are healthy.
Play White by dragging pieces or entering UCI notation (`e2e4`). Promotions offer
queen, rook, bishop, or knight; keyboard users append `q`, `r`, `b`, or `n`.
Drag the network to orbit, scroll to zoom. Use **New game** to reset.

Stop with Ctrl+C, then `docker compose down`. First build needs internet for
packages and images; after building, play requires no external network requests.
Allow roughly 1 GB of free memory for the stack and build tools.

## Cloud deployment

The default Compose deployment is intentionally on-premise. It can also run on
any Linux VM or cloud instance with Docker, but the application is stateful in
memory: use one backend worker and persistent WebSocket support. The simplest
production shape is a small VM with a public reverse proxy or load balancer:

```sh
git clone https://github.com/ebubekir/fly-brain-chess.git
cd fly-brain-chess
cp .env.example .env
# Set ALLOWED_ORIGINS=https://chess.example.com in .env
docker compose up --build -d
```

Put TLS and authentication in front of port 8000. Allow WebSocket upgrades for
`/ws`, route `/api/*` and `/ws` to the same Compose service, and keep backend
worker count at `1`. The container listens on localhost by default; for a cloud
load balancer change the Compose port binding to `0.0.0.0:8000:8080` only when
the host firewall and TLS proxy are configured. Do not expose backend port 8001.

For managed container platforms, deploy the frontend and backend as one service
or use a platform with sticky WebSocket routing. Set `ALLOWED_ORIGINS` to the
exact public origin, configure health checks for `/api/health`, and use at least
512 MiB backend memory and 2 vCPUs. Sessions and games disappear on restart or
redeploy; a Redis-backed session actor and shared worker ownership are required
before horizontal scaling. FlyWire data are baked into the image after the
offline import; no FlyWire API token is needed at runtime.

Cloud checklist: TLS, exact origin allowlist, WebSocket idle timeout ≥100 s,
single backend worker, no public port 8001, log redaction for session URLs,
resource limits, and a backup of `backend/data/readout.npz`,
`backend/data/training_report.json`, and `backend/data/flywire_783.json` when
releasing a trained model. See [`docs/cloud-deployment.md`](docs/cloud-deployment.md)
for provider-neutral and AWS/GCP/Azure examples.

## What is actually happening?

1. **Sense.** Each occupied square activates one of 768 sensory channels
   (64 squares × 6 piece types × 2 colors), with 180 Hz Poisson impulses.
2. **Integrate.** A NetworkX graph connects those channels to 192 recurrent
   interneurons and 132 motor neurons. A NumPy leaky integrate-and-fire solver
   runs **200 simulated milliseconds** in 1 ms steps. Interneurons include
   excitatory and inhibitory cells, synaptic decay, and refractory periods.
3. **Read out.** A linear output layer, trained offline on deterministic
   two-ply teacher examples, scores origin, destination, and promotion heads.
   Only that layer is trainable; FlyWire IDs, synapse counts, and reservoir
   weights remain frozen. There is no search tree or promise of competitive
   strength.
4. **See it.** Ten WebSocket batches stream actual spike counts, intensity,
   node IDs, and positions. Three.js instanced nodes and sampled synaptic pulses
   glow through EffectComposer and UnrealBloomPass. Pulse travel is slowed to
   650 ms for visibility; it does not represent biological conduction speed.

**Scientific boundary:** this uses real FlyWire FAFB v783 neuron IDs and
synapse counts, but the selected PB subgraph, signs, dynamics, chess encoding,
coordinates, and trained readout are engineered. A wiring diagram alone does
not specify neural dynamics or teach chess. The reservoir is fixed and the
model does not learn between games. See `backend/data/training_report.json` for
the dataset fingerprint, split metrics, and limitations.

FlyWire is a collaborative connectomics project, not solely a Google product.
Explore the actual project and available datasets through
[FlyWire Codex](https://codex.flywire.ai/about_flywire) and its
[data access FAQ](https://codex.flywire.ai/faq). Real-data integration should
cite a specific release, preserve its licensing and provenance, and document
neuron selection, connectivity, signs, and chess input/output mapping.

## The code

```text
backend/
  app/
    main.py             FastAPI, WebSocket lifecycle, limits, session recovery
    game.py             Authoritative board, revision, history, result
    neural.py           Frozen FlyWire v783 graph, sensory encoder, LIF reservoir
    readout.py          Fingerprint-checked trained linear policy layer
  training/
    train.py            Offline dataset generation and output-layer training
    teacher.py          Documented weak two-ply imitation teacher
  tests/                Chess, neural, protocol, and recovery tests
  requirements*.txt     Runtime and development dependencies
  Dockerfile
frontend/
  src/
    main.js             UI state and event coordination
    board.js            chessboard.js + chess.js, promotion input
    transport.js        Same-origin WebSocket and reconnect handling
    visualizer.js       Three.js graph, bloom, bounded pulse pool
    style.css           Responsive split-screen workspace
  index.html
  package-lock.json     Reproducible frontend dependency resolution
  nginx.conf            Static hosting and WebSocket reverse proxy
  Dockerfile            Node build → unprivileged Nginx
scripts/import_flywire.py Download and reproducibly select the real subgraph
scripts/smoke.py         Deployed HTTP/WebSocket smoke test
.github/workflows/ci.yml Test and container build pipeline
docs/architecture.md    Model assumptions and system boundaries
docs/protocol.md        WebSocket contract
docker-compose.yml
```

## Operational model

Nginx listens on **127.0.0.1:8000** and proxies to an internal FastAPI service.
Both containers run without root privileges, with read-only filesystems,
resource limits, and health checks. The browser loads all dependencies locally.
The backend validates moves, request revisions, browser origins, packet size,
and command pacing. Slow socket sends time out. Neural work runs off the async
loop with four concurrent trials at most.

Each tab gets a random session capability in `sessionStorage`; treat that token
as access to the game. Reconnects recover the board, including accepted moves
completed while disconnected. One connection can own a session at a time.
A heartbeat refreshes state after reconnects. Up to 128 sessions are retained;
disconnected sessions expire after an hour (cleanup runs every minute).
**Container restart loses games.** This deliberately uses no database, accounts,
or persistent analytics. Run exactly one backend worker; horizontal scaling
requires shared session ownership and storage first.

Claimable threefold/fifty-move draws are automatically accepted for either side.
Checkmate, stalemate, and insufficient material also end games. White is always
the user. The app is a local research/education application, not a rated engine
or a validated biological experiment.

Optional settings are listed in `.env.example`; copy it to `.env` to customize.
For LAN deployment, deliberately change the localhost port binding and set
`ALLOWED_ORIGINS` to the exact browser origin(s). Place remote deployments behind
TLS and your own authentication gateway. The default deployment is local-only.

## Development & verification

Python 3.11+ and Node.js 22+:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
(cd backend && ../.venv/bin/python -m pytest -q)
(cd backend && ../.venv/bin/ruff check app tests)
(cd frontend && npm ci && npm run build)
```

Run the backend:

```sh
cd backend
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173 ../.venv/bin/uvicorn app.main:app --port 8001 --reload
```

In another terminal, `cd frontend && npm run dev`, then open
[localhost:5173](http://localhost:5173). Vite proxies `/api` and `/ws`.
After Docker startup, run `.venv/bin/python scripts/smoke.py` to verify the
public health endpoint and a full streamed turn through Nginx.

Useful diagnostics: `docker compose ps`, `docker compose logs backend`, and
`docker compose logs frontend`. If port 8000 is occupied, stop the conflicting
service or change the port mapping **and** allowed origin. If WebGL2 is
unavailable, chess still works; the visualizer displays a fallback message.

## Contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md). Keep the chess rules, neural model,
transport, and rendering boundaries intact. Add a reproducible test for behavior
changes. Explain scientific assumptions and distinguish measured data from
synthetic choices. Good contributions include data adapters with provenance,
validated model dynamics, decoding experiments, and accessible visualizations.

## License

GPL-3.0-or-later; see [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
This license aligns with the GPL-licensed python-chess dependency. FlyWire data
are not bundled and are not relicensed by this repository.

## Sources

- [FlyWire Codex](https://codex.flywire.ai/)
- [FlyWire data and citation guidelines](https://flywire.ai/guidelines)
- [Nature: Neuronal wiring diagram of an adult brain](https://doi.org/10.1038/s41586-024-07558-y)
- [Google Research: Releasing the Drosophila hemibrain connectome](https://research.google/blog/releasing-the-drosophila-hemibrain-connectome-the-largest-synapse-resolution-map-of-brain-connectivity/)
- [Google Research: Mapping the complete male fruit fly brain](https://research.google/blog/a-connectomics-milestone-mapping-the-complete-male-fruit-fly-brain/)
- [Nature: A Drosophila computational brain model reveals sensorimotor processing](https://doi.org/10.1038/s41586-024-07763-9)
