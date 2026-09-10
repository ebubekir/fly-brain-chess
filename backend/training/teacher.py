"""Small deterministic two-ply teacher, used ONLY for offline imitation labels.

This handcrafted evaluator is not Stockfish and carries no strength claim.
"""
import chess

VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


def evaluate(board: chess.Board, color: chess.Color) -> float:
    value = 0.0
    for square, piece in board.piece_map().items():
        rank = chess.square_rank(square) if piece.color else 7 - chess.square_rank(square)
        center = 7 - abs(chess.square_file(square) - 3.5) - abs(chess.square_rank(square) - 3.5)
        bonus = center * (8 if piece.piece_type in (chess.KNIGHT, chess.BISHOP) else 2)
        if piece.piece_type == chess.PAWN:
            bonus += rank * 9
        value += (VALUES[piece.piece_type] + bonus) * (1 if piece.color == color else -1)
    return value


def choose(board: chess.Board) -> chess.Move:
    color = board.turn
    best, best_score = None, -float('inf')
    for move in sorted(board.legal_moves, key=lambda m: m.uci()):
        board.push(move)
        if board.is_checkmate():
            score = 100000
        elif board.is_stalemate() or board.is_insufficient_material():
            score = 0
        else:
            score = float('inf')
            for reply in board.legal_moves:
                board.push(reply)
                value = evaluate(board, color)
                board.pop()
                score = min(score, value)
                if score <= best_score:
                    break
        board.pop()
        if score > best_score:
            best, best_score = move, score
    if best is None:
        raise ValueError('Teacher requires a non-terminal position')
    return best
