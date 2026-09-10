"""Regressions for the real frozen reservoir and trained-only readout."""
import numpy as np
import chess
import pytest
from app.neural import Connectome, Simulation
from app.readout import Readout, action_indices


def test_graph_retains_real_source_ids_and_counts():
    graph = Connectome()
    assert graph.serialize()['kind'] == 'flywire-fafb-783'
    assert graph.size == 256
    assert all(len(n['root_id']) == 18 for _, n in graph.graph.nodes(data=True))
    assert all(d['syn_count'] > 0 for _, _, d in graph.graph.edges(data=True))
    assert not graph.weights.flags.writeable


def test_promotion_actions_are_distinct():
    assert action_indices(chess.Move.from_uci('a7a8q')) != action_indices(chess.Move.from_uci('a7a8n'))


def test_readout_is_only_decision_path_and_neural_weights_stay_fixed():
    graph = Connectome()
    before = graph.weights.copy()
    sim = Simulation(graph, chess.Board())
    for _ in range(10):
        sim.advance()
    moves = sorted(sim.board.legal_moves, key=lambda m: m.uci())
    logits = graph.readout.logits(sim.features())
    expected = max(moves, key=lambda m: sum(logits[i] for i in action_indices(m)))
    assert sim.decode() == expected
    np.testing.assert_array_equal(graph.weights, before)


def test_checkpoint_mismatch_fails_closed(tmp_path):
    graph = Connectome()
    path = tmp_path / 'bad.npz'
    np.savez(path, weights=np.zeros((graph.size + 1, 132)), mean=np.zeros(graph.size), scale=np.ones(graph.size), reservoir_fingerprint=np.array('wrong'))
    with pytest.raises(ValueError, match='fingerprint'):
        Readout(path, graph.fingerprint, graph.size)
