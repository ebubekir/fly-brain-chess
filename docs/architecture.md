# Architecture

The deployment is deliberately local: a static ES-module frontend behind Nginx
(port 8000) and one internal FastAPI process (port 8001). There are no runtime
cloud services, remote fonts, or CDN scripts. npm and pip need internet at build
time. The NetworkX topology and NumPy LIF solver avoid Brian2 compilation cost.

White is human, Black is a FlyWire-reservoir policy. The frozen reservoir is an
induced PB subgraph of 256 real FAFB v783 neurons and 3,227 recorded directed
edges. The reservoir is driven by 768 engineered piece/color/square channels;
its coordinates, neuron dynamics, signs, and output action heads are engineered.
Only the 132-action linear readout was trained offline.

For each position, occupied sensory channels receive 180 Hz Poisson input.
The solver uses 1 ms Euler steps, a 20 ms membrane constant, 5 ms synaptic decay,
threshold/reset and 3 ms refractory periods. Each actual integration batch
produces a WebSocket frame after 20 simulated ms; ten batches complete a move.
Motor counts over 200 ms rank legal origin/destination/promotion combinations.
A small explicit capture/check/center heuristic helps tie-breaking and playability;
there is no search engine or hidden Stockfish move selection. Randomness derives
from the complete FEN and topology seed, making trials reproducible.

Authoritative state lives in bounded, expiring in-memory sessions; a random
session capability is stored in sessionStorage. A reconnect resumes the same
game. One socket owns a session at a time. Commands use revision preconditions,
server chess validation, bounded size/rate, and origin checks. An accepted move
finishes even if the viewer disconnects. Sessions do not survive process restart.
Scale requires a shared store/actor design; adding Uvicorn workers is unsupported.

Frontend modules separate transport, board input, and GPU rendering. Instanced
nodes, line segments, and a bounded pool of moving points animate actual spiking
sources. Visual pulse traversal is slowed for legibility; it is not axonal travel
time. GPU failure leaves the chess interface functional. Reduced-motion support
stops auto-rotation and traveling pulses. Keyboard users can submit UCI moves.

Verification covers deterministic encoding/spikes, legal decoding, special chess
positions, stale requests, malformed packets, isolation, and reconnection. CI
also builds the frontend and both container images. Local deployment validation
checks the Nginx health endpoint and a full WebSocket human/brain turn.
