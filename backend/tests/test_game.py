import chess
from app.game import Game


def test_castling_en_passant_and_underpromotion():
    for fen, uci, target, piece in [
        ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1", chess.F1, chess.ROOK),
        ("7k/8/8/3pP3/8/8/8/K7 w - d6 0 1", "e5d6", chess.D6, chess.PAWN),
        ("7k/P7/8/8/8/8/8/7K w - - 0 1", "a7a8n", chess.A8, chess.KNIGHT),
    ]:
        game = Game(board=chess.Board(fen))
        move = chess.Move.from_uci(uci)
        assert move in game.board.legal_moves
        game.push(move)
        assert game.board.piece_at(target).piece_type == piece
        assert game.revision == 1
        if uci == "e5d6":
            assert game.board.piece_at(chess.D5) is None


def test_checkmate_and_claimable_draw_are_terminal():
    game = Game()
    for uci in ["f2f3", "e7e5", "g2g4", "d8h4"]:
        game.push(chess.Move.from_uci(uci))
    assert game.snapshot()["result"] == "0-1"
    assert game.snapshot()["termination"] == "checkmate"
    assert game.snapshot()["legal_moves"] == []
    game.reset()
    for uci in ["g1f3", "g8f6", "f3g1", "f6g8"] * 2:
        game.push(chess.Move.from_uci(uci))
    assert game.snapshot()["result"] == "1/2-1/2"
    assert game.snapshot()["termination"] == "threefold_repetition"
