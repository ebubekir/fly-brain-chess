/** Same-origin WebSocket with session resumption and bounded reconnect backoff. */
export class Transport {
  constructor(onMessage, onStatus) {
    this.onMessage = onMessage;
    this.onStatus = onStatus;
    this.retry = 0;
    this.stopped = false;
    this.connect();
    this.heartbeat = setInterval(() => this.send({ type: "ping" }), 2000);
  }
  connect() {
    if (this.stopped) return;
    const url = new URL("/ws", location.href);
    url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
    try {
      const token = sessionStorage.getItem("fly-session");
      if (token) url.searchParams.set("session", token);
    } catch {
      /* Storage may be disabled. */
    }
    this.socket = new WebSocket(url);
    this.onStatus(false, "Connecting");
    this.socket.onopen = () => {
      this.retry = 0;
      this.onStatus(true, "Connected locally");
    };
    this.socket.onmessage = ({ data }) => {
      try {
        const message = JSON.parse(data);
        if (message.type === "hello") {
          try {
            sessionStorage.setItem("fly-session", message.session_id);
          } catch {
            /* In-memory session still works. */
          }
        }
        this.onMessage(message);
      } catch (error) {
        console.error("Unable to process server message", error);
      }
    };
    this.socket.onclose = ({ code }) => {
      if (this.stopped) return;
      this.onStatus(
        false,
        code === 4009 ? "Session open elsewhere; retrying" : "Reconnecting…",
      );
      this.timer = setTimeout(
        () => this.connect(),
        Math.min(15000, 500 * 2 ** this.retry++),
      );
    };
  }
  send(message) {
    if (this.socket.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(message));
    return true;
  }
  dispose() {
    this.stopped = true;
    clearTimeout(this.timer);
    clearInterval(this.heartbeat);
    this.socket.close();
  }
}
