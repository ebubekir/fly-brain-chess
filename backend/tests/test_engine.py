import chess
import numpy as np
import pytest
from app.neural import Connectome, Simulation


def test_encoding_distinguishes_piece_color_and_square():
    graph = Connectome()
    before = graph.encode(chess.Board())
    board = chess.Board()
    board.push_uci("e2e4")
    assert not np.array_equal(before, graph.encode(board))
    assert before.shape == (graph.size,)


def test_simulation_is_reproducible_and_decodes_legal_move():
    graph = Connectome()
    board = chess.Board()
    board.push_uci("e2e4")
    a, b = Simulation(graph, board), Simulation(graph, board)
    frames = [a.advance() for _ in range(10)]
    assert frames == [b.advance() for _ in range(10)]
    assert frames[-1]["time_ms"] == 200
    assert sum(len(frame["spikes"]) for frame in frames) > 0
    assert a.decode() in board.legal_moves
    assert board.fullmove_number == 1
    for frame in frames:
        for spike in frame["spikes"]:
            assert 0 <= spike["id"] < graph.size
            assert 0 < spike["intensity"] <= 1
            assert len(spike["position"]) == 3
    with pytest.raises(RuntimeError):
        a.advance()


@pytest.mark.parametrize(
    "fen",
    [
        "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1",
        "7k/8/8/8/8/8/p6K/8 b - - 0 1",
        "7k/8/8/8/3pP3/8/8/K7 b - e3 0 1",
        "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1",
    ],
)
def test_decoder_special_positions(fen):
    board = chess.Board(fen)
    sim = Simulation(Connectome(), board)
    for _ in range(10):
        sim.advance()
    move = sim.decode()
    assert move in board.legal_moves if board.legal_moves else move is None
