"""Frozen real FlyWire subgraph, engineered chess inputs, and a fitted readout.

Connectivity/counts/IDs are empirical. Layout, dynamic parameters, input mapping,
and the readout are engineered. This is not a reconstruction of fly cognition.
"""
import hashlib
import json
from pathlib import Path

import chess
import networkx as nx
import numpy as np

from .readout import Readout, action_indices

DATA = Path(__file__).resolve().parents[1] / 'data'
CONFIG = {
    'version': 1, 'seed': 42, 'dt_ms': 1, 'duration_ms': 200,
    'membrane_tau_ms': 20, 'synapse_tau_ms': 5, 'refractory_ms': 3,
    'threshold': 1.0, 'background': 0.15, 'input_rate_hz': 180,
    'input_fanout': 3, 'input_impulse': 6.0, 'incoming_gain': 4.0,
    'signs': {'ACH': 1, 'GABA': -1, 'GLUT': -1},
    'features': 'spike-counts / 20 (100Hz units)',
}


class Connectome:
    def __init__(self, *, load_readout: bool = True):
        self.seed = CONFIG['seed']
        raw = (DATA / 'flywire_783.json').read_bytes()
        data = json.loads(raw)
        self.provenance = data['provenance']
        self.fingerprint = hashlib.sha256(raw + json.dumps(CONFIG, sort_keys=True).encode()).hexdigest()
        self.size = len(data['nodes'])
        self.graph = nx.DiGraph()
        index = {n['root_id']: i for i, n in enumerate(data['nodes'])}
        if len(index) != self.size:
            raise ValueError('Duplicate root IDs')
        for i, node in enumerate(data['nodes']):
            inhibitory = CONFIG['signs'][node['nt_type']] < 0
            self.graph.add_node(i, **node, role='inhibitory' if inhibitory else 'excitatory', inhibitory=inhibitory)
        for edge in data['edges']:
            a, b = index[edge['pre_root_id']], index[edge['post_root_id']]
            self.graph.add_edge(a, b, syn_count=edge['syn_count'], neuropils=edge['neuropils'])
        # Preserve all selected edges and raw counts; use a documented normalization
        # for numerical stability rather than pretending counts are conductances.
        incoming = dict(self.graph.in_degree(weight='syn_count'))
        for a, b, edge in self.graph.edges(data=True):
            edge['weight'] = CONFIG['signs'][self.graph.nodes[a]['nt_type']] * CONFIG['incoming_gain'] * edge['syn_count'] / incoming[b]
        layout = nx.spring_layout(self.graph, dim=3, seed=self.seed, weight='syn_count', iterations=60)
        self.positions = [[round(float(v * 65), 3) for v in layout[i]] for i in range(self.size)]
        for i, position in enumerate(self.positions):
            self.graph.nodes[i]['position'] = position
        edges = list(self.graph.edges(data=True))
        self.sources = np.array([a for a, _, _ in edges], dtype=int)
        self.targets = np.array([b for _, b, _ in edges], dtype=int)
        self.weights = np.array([d['weight'] for _, _, d in edges])
        rng = np.random.default_rng(self.seed)
        self.input_projection = np.zeros((768, self.size))
        for row in self.input_projection:
            row[rng.choice(self.size, CONFIG['input_fanout'], replace=False)] = 1
        for a in [self.sources, self.targets, self.weights, self.input_projection]:
            a.flags.writeable = False
        nx.freeze(self.graph)
        self.readout = Readout(DATA / 'readout.npz', self.fingerprint, self.size) if load_readout else None

    def encode(self, board: chess.Board) -> np.ndarray:
        channels = np.zeros(768)
        for square, piece in board.piece_map().items():
            channel = (0 if piece.color else 6) + piece.piece_type - 1
            channels[channel * 64 + square] = CONFIG['input_rate_hz']
        return channels @ self.input_projection

    def serialize(self) -> dict:
        return {
            'kind': 'flywire-fafb-783', 'seed': self.seed, 'fingerprint': self.fingerprint,
            'provenance': self.provenance,
            'readout': 'trained-linear-policy' if self.readout else 'not-loaded',
            'nodes': [{'id': i, **data} for i, data in self.graph.nodes(data=True)],
            'edges': [{'source': a, 'target': b, 'weight': d['weight'], 'syn_count': d['syn_count']} for a, b, d in self.graph.edges(data=True)],
        }


class Simulation:
    """One reproducible trial. Training cannot alter reservoir state or connectivity."""
    def __init__(self, graph: Connectome, board: chess.Board):
        self.graph = graph
        self.board = board.copy()
        # Common random numbers across positions reduce encoding noise.
        self.rng = np.random.default_rng(graph.seed)
        self.rates = graph.encode(board)
        self.voltage = np.zeros(graph.size)
        self.current = np.zeros(graph.size)
        self.refractory = np.zeros(graph.size, dtype=int)
        self.counts = np.zeros(graph.size, dtype=int)
        self.time_ms = 0

    def advance(self) -> dict:
        if self.time_ms >= CONFIG['duration_ms']:
            raise RuntimeError('Simulation has already completed')
        counts = np.zeros(self.graph.size, dtype=int)
        for _ in range(20):
            self.current *= np.exp(-CONFIG['dt_ms'] / CONFIG['synapse_tau_ms'])
            self.current += self.rng.poisson(self.rates / 1000) * CONFIG['input_impulse']
            self.refractory = np.maximum(0, self.refractory - 1)
            available = self.refractory == 0
            self.voltage[available] += (-self.voltage[available] + CONFIG['background'] + self.current[available]) / CONFIG['membrane_tau_ms']
            spikes = (self.voltage >= CONFIG['threshold']) & available
            self.voltage[spikes] = 0
            self.refractory[spikes] = CONFIG['refractory_ms']
            active = spikes[self.graph.sources]
            self.current += np.bincount(self.graph.targets[active], weights=self.graph.weights[active], minlength=self.graph.size)
            counts += spikes
            self.time_ms += 1
        self.counts += counts
        return {'type': 'spikes', 'time_ms': self.time_ms, 'duration_ms': 20,
                'spikes': [{'id': int(i), 'count': int(counts[i]), 'intensity': min(1.0, float(counts[i]) / 4), 'position': self.graph.positions[i]} for i in np.flatnonzero(counts)]}

    def features(self) -> np.ndarray:
        if self.time_ms != CONFIG['duration_ms']:
            raise RuntimeError('Readout requires a completed 200 ms trial')
        return self.counts.astype(float) / 20

    def decode(self) -> chess.Move | None:
        if self.graph.readout is None:
            raise RuntimeError('No trained readout is loaded')
        logits = self.graph.readout.logits(self.features())
        legal = sorted(self.board.legal_moves, key=lambda m: m.uci())
        # No material/check bonuses or chess teacher are consulted during play.
        return max(legal, key=lambda m: sum(logits[i] for i in action_indices(m))) if legal else None

    def summary(self) -> dict:
        return {'total_spikes': int(self.counts.sum()), 'active_neurons': int(np.count_nonzero(self.counts)),
                'duration_ms': self.time_ms, 'model': 'flywire-fafb-783', 'readout': 'trained-linear-policy'}
