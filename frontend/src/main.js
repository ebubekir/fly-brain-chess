import "./style.css";
import { BoardView } from "./board.js";
import { NeuralView } from "./visualizer.js";
import { Transport } from "./transport.js";

const $ = (id) => document.getElementById(id);
let state = null,
  connected = false,
  pending = false,
  visualizer;
let lastRevision = -1,
  trialRevision = -1,
  spikeCount = 0;
try {
  visualizer = new NeuralView($("visualizer"));
} catch (error) {
  $("gpu-error").hidden = false;
  console.warn("3D view unavailable", error);
}
const board = new BoardView(sendMove);

function render(next) {
  state = next;
  pending = false;
  board.update(state, connected);
  $("reset").disabled = !connected || state.thinking;
  $("move-submit").disabled = !board.enabled;
  $("move-input").disabled = !board.enabled;
  $("status").textContent = !connected
    ? "Connection lost. Reconnecting…"
    : state.result
      ? `${state.result} · ${state.termination.replaceAll("_", " ")}`
      : state.thinking
        ? "The brain is thinking…"
        : state.turn === "white"
          ? `Your move${state.check ? " · You are in check" : ""}`
          : "Waiting for the brain…";
  $("turn-dot").classList.toggle("thinking", state.thinking);
  if (!state.thinking) {
    $("activity-label").textContent = state.stats.duration_ms
      ? "Motor response decoded · Ready for your move"
      : "Waiting for sensory input";
    $("sim-time").textContent = `${state.stats.duration_ms || 0} / 200 ms`;
    $("progress").style.width = state.stats.duration_ms ? "100%" : "0%";
    $("spike-count").textContent = (
      state.stats.total_spikes || 0
    ).toLocaleString();
    $("motor-count").textContent = (
      state.stats.active_neurons || 0
    ).toLocaleString();
  }
  if (lastRevision !== state.revision) {
    lastRevision = state.revision;
    $("history").replaceChildren();
    if (!state.history.length) {
      const item = document.createElement("li");
      item.className = "empty";
      item.textContent = "The first move is yours.";
      $("history").append(item);
    }
    for (let i = 0; i < state.history.length; i += 2) {
      const item = document.createElement("li");
      item.textContent = `${i / 2 + 1}.  ${state.history[i].san}   ${state.history[i + 1]?.san || "…"}`;
      $("history").append(item);
    }
    $("history").scrollLeft = $("history").scrollWidth;
  }
}
function sendMove(uci) {
  if (!state || !board.enabled || pending) return;
  if (!state.legal_moves.includes(uci)) {
    $("error").textContent =
      "Enter a legal move, for example e2e4. Add q, r, b, or n for promotion.";
    return;
  }
  $("error").textContent = "";
  pending = transport.send({ type: "move", uci, revision: state.revision });
  if (pending) {
    board.enabled = false;
    $("move-submit").disabled = true;
    $("move-input").value = "";
  }
}
const transport = new Transport(
  (message) => {
    if (message.type === "hello") {
      lastRevision = -1;
      visualizer?.setGraph(message.graph);
      $("neuron-count").textContent =
        message.graph.nodes.length.toLocaleString();
      $("edge-count").textContent = message.graph.edges.length.toLocaleString();
    } else if (message.type === "state" || message.type === "pong") {
      render(message.state || message);
    } else if (message.type === "error") {
      render(message.state);
      $("error").textContent = message.message;
    } else if (message.type === "spikes") {
      if (trialRevision !== message.revision || message.time_ms === 20) {
        trialRevision = message.revision;
        spikeCount = 0;
      }
      spikeCount += message.spikes.reduce((sum, spike) => sum + spike.count, 0);
      $("spike-count").textContent = spikeCount.toLocaleString();
      $("sim-time").textContent = `${message.time_ms} / 200 ms`;
      $("progress").style.width = `${message.time_ms / 2}%`;
      $("activity-label").textContent =
        "Integrating sensory input → motor activity";
      visualizer?.spike(message);
    }
  },
  (online, label) => {
    connected = online;
    $("connection").textContent = label;
    $("connection-dot").classList.toggle("online", online);
    if (state) render(state);
  },
);
$("move-form").addEventListener("submit", (event) => {
  event.preventDefault();
  sendMove($("move-input").value.trim().toLowerCase());
});
$("reset").addEventListener("click", () => {
  if (!state || pending || state.thinking) return;
  $("error").textContent = "";
  pending = transport.send({ type: "reset", revision: state.revision });
  $("reset").disabled = pending;
});
window.addEventListener("pagehide", () => {
  transport.dispose();
  board.dispose();
  visualizer?.dispose();
});
window.addEventListener("pageshow", (event) => {
  if (event.persisted) location.reload();
});
