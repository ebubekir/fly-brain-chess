"""Only trainable component: a linear policy over origin/destination/promotion heads."""
from pathlib import Path
import chess
import numpy as np

PROMOTIONS = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]
HEADS = 132


def action_indices(move: chess.Move) -> tuple[int, ...]:
    heads = (move.from_square, 64 + move.to_square)
    return heads + (128 + PROMOTIONS.index(move.promotion),) if move.promotion else heads


class Readout:
    def __init__(self, path: Path, fingerprint: str, size: int):
        with np.load(path, allow_pickle=False) as data:
            if str(data['reservoir_fingerprint']) != fingerprint:
                raise ValueError('Readout reservoir fingerprint mismatch; retrain for this graph/configuration')
            self.weights = data['weights'].copy()
            self.mean = data['mean'].copy()
            self.scale = data['scale'].copy()
        if self.weights.shape != (size + 1, HEADS) or self.mean.shape != (size,) or self.scale.shape != (size,):
            raise ValueError('Invalid readout dimensions')
        if not all(np.isfinite(a).all() for a in [self.weights, self.mean, self.scale]) or (self.scale <= 0).any():
            raise ValueError('Invalid readout numeric values')
        for array in [self.weights, self.mean, self.scale]:
            array.flags.writeable = False

    def logits(self, features: np.ndarray) -> np.ndarray:
        normalized = (features - self.mean) / self.scale
        return np.append(normalized, 1) @ self.weights
