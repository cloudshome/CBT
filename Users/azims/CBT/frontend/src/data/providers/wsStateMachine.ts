/**
 * Formalized WebSocket Connection Lifecycle State Machine.
 *
 * States:
 *   IDLE -> CONNECTING -> CONNECTED -> (HEARTBEAT) -> RECONNECTING -> DISCONNECTED
 *
 * Features:
 *   - Exponential backoff with randomized jitter
 *   - Heartbeat staleness watchdog (detects silent TCP drops)
 *   - Observable state transitions for UI diagnostic telemetry
 */

export type WSConnectionState =
  | 'IDLE'
  | 'CONNECTING'
  | 'CONNECTED'
  | 'RECONNECTING'
  | 'DISCONNECTED'
  | 'ERROR';

export interface WSStateMachineOptions {
  url: string;
  initialBackoffMs?: number; // default: 1000ms
  maxBackoffMs?: number;     // default: 30000ms
  heartbeatTimeoutMs?: number; // default: 20000ms
  onMessage?: (event: MessageEvent) => void;
  onStateChange?: (state: WSConnectionState, attempt: number) => void;
}

export class WSStateMachine {
  private url: string;
  private ws: WebSocket | null = null;
  private state: WSConnectionState = 'IDLE';
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
  private lastMessageTime = 0;

  private readonly initialBackoffMs: number;
  private readonly maxBackoffMs: number;
  private readonly heartbeatTimeoutMs: number;
  private readonly onMessage?: (event: MessageEvent) => void;
  private readonly onStateChange?: (state: WSConnectionState, attempt: number) => void;

  constructor(options: WSStateMachineOptions) {
    this.url = options.url;
    this.initialBackoffMs = options.initialBackoffMs ?? 1000;
    this.maxBackoffMs = options.maxBackoffMs ?? 30000;
    this.heartbeatTimeoutMs = options.heartbeatTimeoutMs ?? 20000;
    this.onMessage = options.onMessage;
    this.onStateChange = options.onStateChange;
  }

  public getState(): WSConnectionState {
    return this.state;
  }

  public getAttempt(): number {
    return this.reconnectAttempt;
  }

  public setUrl(newUrl: string): void {
    if (this.url !== newUrl) {
      this.url = newUrl;
      if (this.state === 'CONNECTED' || this.state === 'CONNECTING') {
        this.disconnect();
        this.connect();
      }
    }
  }

  public connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.transitionTo('CONNECTING');
    this.clearTimers();

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.reconnectAttempt = 0;
        this.lastMessageTime = Date.now();
        this.transitionTo('CONNECTED');
        this.startHeartbeatWatchdog();
      };

      this.ws.onmessage = (event) => {
        this.lastMessageTime = Date.now();
        this.resetHeartbeatWatchdog();
        this.onMessage?.(event);
      };

      this.ws.onerror = () => {
        this.transitionTo('ERROR');
      };

      this.ws.onclose = () => {
        if (this.state !== 'DISCONNECTED') {
          this.scheduleReconnect();
        }
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  public disconnect(): void {
    this.transitionTo('DISCONNECTED');
    this.clearTimers();
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }

  private scheduleReconnect(): void {
    this.transitionTo('RECONNECTING');
    this.clearTimers();

    this.reconnectAttempt += 1;
    // Exponential backoff: min(maxBackoff, initialBackoff * 2^(attempt-1)) + jitter
    const backoff = Math.min(
      this.maxBackoffMs,
      this.initialBackoffMs * Math.pow(2, this.reconnectAttempt - 1)
    );
    const jitter = Math.random() * 500;
    const delay = backoff + jitter;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startHeartbeatWatchdog(): void {
    this.clearHeartbeatWatchdog();
    this.heartbeatTimer = setInterval(() => {
      const now = Date.now();
      if (now - this.lastMessageTime > this.heartbeatTimeoutMs) {
        // Silent connection drop detected — force reconnect
        if (this.ws) {
          this.ws.close();
        }
      }
    }, 5000);
  }

  private resetHeartbeatWatchdog(): void {
    // Keep active
  }

  private clearHeartbeatWatchdog(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private clearTimers(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.clearHeartbeatWatchdog();
  }

  private transitionTo(newState: WSConnectionState): void {
    if (this.state !== newState) {
      this.state = newState;
      this.onStateChange?.(newState, this.reconnectAttempt);
    }
  }
}
