import $ from "jquery";
import { Chess } from "chess.js";
import "@chrisoakman/chessboardjs/dist/chessboard-1.0.0.min.css";
// chessboard.js is a legacy UMD widget; it requires jQuery before evaluation.
window.$ = window.jQuery = $;
await import("@chrisoakman/chessboardjs/dist/chessboard-1.0.0.min.js");

export class BoardView {
  constructor(onMove) {
    this.chess = new Chess();
    this.enabled = false;
    this.onMove = onMove;
    this.dialog = document.querySelector("#promotion");
    this.board = window.Chessboard("board", {
      position: "start",
      draggable: true,
      pieceTheme: (piece) => `/pieces/${piece}.svg`,
      onDragStart: (_source, piece) => this.enabled && piece.startsWith("w"),
      onDrop: (source, target) => {
        this.attempt(source, target);
        return "snapback";
      },
    });
    this.observer = new ResizeObserver(() => this.board.resize());
    this.observer.observe(document.querySelector(".board-panel"));
  }
  async attempt(source, target) {
    if (!this.enabled) return;
    const candidates = this.chess
      .moves({ verbose: true })
      .filter((m) => m.from === source && m.to === target);
    if (!candidates.length) return;
    let promotion = "";
    if (candidates.some((m) => m.promotion)) {
      if (this.dialog.open) return;
      this.dialog.returnValue = "cancel";
      this.dialog.showModal();
      promotion = await new Promise((resolve) =>
        this.dialog.addEventListener(
          "close",
          () => resolve(this.dialog.returnValue),
          { once: true },
        ),
      );
      if (!["q", "r", "b", "n"].includes(promotion) || !this.enabled) return;
    }
    this.onMove(source + target + promotion);
  }
  update(state, connected) {
    this.chess.load(state.fen);
    this.board.position(state.fen, true);
    this.enabled =
      connected && !state.thinking && state.turn === "white" && !state.result;
  }
  dispose() {
    this.observer.disconnect();
    this.board.destroy();
  }
}
