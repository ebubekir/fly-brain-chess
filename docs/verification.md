# Verification record

Verified locally on 2026-09-10:

- 14 pytest tests pass: deterministic simulation, sensory encoding, legal motor
  decoding, castling, en passant, underpromotion, checkmate, claimable draws,
  WebSocket validation, revision checks, session isolation, duplicate connection
  rejection, untrusted Origin rejection, and disconnect recovery.
- Ruff checks pass for backend application and tests.
- Vite production build passes, with locally served SVG pieces.
- npm audit and pip-audit of runtime requirements report no known vulnerabilities
  at verification time. This is a point-in-time dependency check, not a security
  certification.
- Docker Compose builds and starts both containers with healthy status.
- scripts/smoke.py passes through Nginx: health endpoint, 1,092 nodes, ten actual
  20 ms activity batches, 200 ms simulation, and a legal Black reply.
- In-app browser: 3D graph renders; local piece assets load; keyboard e2e4 and
  dragged g1f3 receive legal replies; reload restores move history; New game
  resets the board. No browser warning/error logs were observed.

The Python test environment emits upstream Starlette/httpx and AnyIO deprecation
warnings; assertions pass. No load certification, biological validation, rated
chess strength evaluation, or cross-browser/device certification is claimed.
