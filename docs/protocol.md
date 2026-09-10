# WebSocket protocol v1

Connect to `/ws`, optionally with `?session=<opaque capability>` to resume.
The browser Origin must be in `ALLOWED_ORIGINS`. Non-browser clients without
Origin are permitted for local tooling. The token is a bearer capability, not
an identity. Do not share URLs containing it.

Server sends `hello` with `session_id` and `graph`, followed by `state`.
Graph node IDs are contiguous array indices mapped to real FlyWire `root_id`
values in the `provenance` metadata. Nodes include transmitter, role,
inhibitory flag, and synthetic `[x,y,z]` layout position. Directed edges include
source, target, raw `syn_count`, and signed normalized weight. Graph kind is
`flywire-fafb-783`; the response includes the reservoir fingerprint and
training-readout status.

Client messages:

```json
{"type":"move","uci":"e2e4","revision":0}
{"type":"reset","revision":2}
{"type":"ping"}
```

State messages contain `fen`, `revision`, `thinking`, `history` (UCI and SAN),
`legal_moves`, `turn`, `check`, `result`, `termination`, and `stats`.
Result is null or a chess result string. Revision increments with each ply and
reset. A successful human move emits state with `thinking: true`, ten `spikes`
frames, and a final state with the brain's move. A terminal human move emits
only final state. Legal moves are empty after a terminal result.

Example spike batch (the array includes every node that fired in the batch):

```json
{"type":"spikes","revision":1,"time_ms":20,"duration_ms":20,"spikes":[{"id":12,"count":2,"intensity":0.5,"position":[1,2,3]}]}
```

`count` is actual spikes in 20 ms. `intensity = min(1, count / 4)` is a visual
mapping. Coordinates are a seeded visualization layout and unitless. Frame times progress to 200;
wall time may exceed 200 ms under load. The simulation's decision is made only
after all ten batches. The viewer samples outgoing edges for pulse rendering.

Errors use `type: error`, `code`, `message`, and authoritative `state`.
Codes: `invalid_message`, `illegal_move`, `wrong_turn`, `stale_revision`, `busy`,
`rate_limited`, `simulation_failed`. Clients must resynchronize from that state.
`pong` also contains `state`, allowing recovery if a trial completed on an old
connection. The frontend pings every two seconds; idle sockets expire at 90 s.
Reset is rejected while thinking. A disconnected accepted move still completes.

Messages are limited to 2 KiB; binary packets are rejected. Close codes:
1008 forbidden origin, 1009 oversized/binary data, 1013 capacity exhausted,
4009 session already connected. Retry with backoff. Sessions expire after the
configured idle TTL; unknown/expired tokens create a fresh session. Restarting
the single backend process resets all sessions.
