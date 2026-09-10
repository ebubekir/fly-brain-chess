"""Authoritative chess state, independent of transport and neural solver."""

from dataclasses import dataclass, field
import time

import chess


@dataclass
class Game:
    board: chess.Board = field(default_factory=chess.Board)
    revision: int = 0
    thinking: bool = False
    history: list = field(default_factory=list)
    last_seen: float = field(default_factory=time.monotonic)
    connected: bool = False
    stats: dict = field(default_factory=dict)

    def push(self, move: chess.Move):
        self.history.append({"uci": move.uci(), "san": self.board.san(move)})
        self.board.push(move)
        self.revision += 1

    def reset(self):
        self.board.reset()
        self.history.clear()
        self.stats.clear()
        self.revision += 1

    def snapshot(self):
        # This application automatically accepts claimable draws for either side.
        outcome = self.board.outcome(claim_draw=True)
        return {
            "type": "state",
            "fen": self.board.fen(),
            "revision": self.revision,
            "thinking": self.thinking,
            "history": self.history,
            "legal_moves": [m.uci() for m in self.board.legal_moves] if not outcome else [],
            "turn": "white" if self.board.turn else "black",
            "check": self.board.is_check(),
            "result": outcome.result() if outcome else None,
            "termination": outcome.termination.name.lower() if outcome else None,
            "stats": self.stats,
        }
