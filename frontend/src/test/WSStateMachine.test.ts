import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { WSStateMachine, WSConnectionState } from '../data/providers/wsStateMachine';

// Mock WebSocket implementation for headless DOM environment
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  public readyState = MockWebSocket.CONNECTING;
  public url: string;
  public onopen: (() => void) | null = null;
  public onmessage: ((event: MessageEvent) => void) | null = null;
  public onerror: ((event: Event) => void) | null = null;
  public onclose: ((event: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  static instances: MockWebSocket[] = [];
  static reset() {
    MockWebSocket.instances = [];
  }

  public simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    if (this.onopen) this.onopen();
  }

  public simulateMessage(data: string) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data }));
    }
  }

  public simulateClose(code = 1000, reason = 'Normal closure') {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new CloseEvent('close', { code, reason }));
    }
  }

  public simulateError() {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }

  public close() {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new CloseEvent('close', { code: 1000, reason: 'Client closed' }));
    }
  }
}

describe('WSStateMachine Lifecycle & Heartbeat Watchdog', () => {
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.reset();
    originalWebSocket = globalThis.WebSocket;
    // @ts-expect-error Mocking global WebSocket
    globalThis.WebSocket = MockWebSocket;
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    globalThis.WebSocket = originalWebSocket;
  });

  it('initializes in IDLE state', () => {
    const sm = new WSStateMachine({ url: 'wss://example.com/ws' });
    expect(sm.getState()).toBe('IDLE');
    expect(sm.getAttempt()).toBe(0);
  });

  it('transitions to CONNECTING upon connect() and opens properly', () => {
    const stateHistory: WSConnectionState[] = [];
    const sm = new WSStateMachine({
      url: 'wss://example.com/ws',
      onStateChange: (state) => stateHistory.push(state),
    });

    sm.connect();
    expect(sm.getState()).toBe('CONNECTING');
    expect(MockWebSocket.instances.length).toBe(1);

    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();

    expect(sm.getState()).toBe('CONNECTED');
    expect(stateHistory).toEqual(['CONNECTING', 'CONNECTED']);
  });

  it('dispatches messages and updates lastMessageTime', () => {
    let receivedData = '';
    const sm = new WSStateMachine({
      url: 'wss://example.com/ws',
      onMessage: (ev) => {
        receivedData = ev.data;
      },
    });

    sm.connect();
    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();

    ws.simulateMessage(JSON.stringify({ price: 65000 }));
    expect(receivedData).toBe('{"price":65000}');
    expect(sm.getLastMessageTime()).toBeGreaterThan(0);
  });

  it('triggers exponential backoff reconnect on unexpected disconnect', () => {
    const states: WSConnectionState[] = [];
    const sm = new WSStateMachine({
      url: 'wss://example.com/ws',
      initialBackoffMs: 1000,
      onStateChange: (state) => states.push(state),
    });

    sm.connect();
    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();

    // Sudden network drop
    ws.simulateClose(1006, 'Abnormal Closure');
    expect(sm.getState()).toBe('RECONNECTING');
    expect(sm.getAttempt()).toBe(1);

    // Fast-forward backoff time (1000ms + jitter)
    vi.advanceTimersByTime(2000);
    expect(sm.getState()).toBe('CONNECTING');
    expect(MockWebSocket.instances.length).toBe(2);
  });

  it('heartbeat watchdog detects silent stale connection and reconnects', () => {
    const states: WSConnectionState[] = [];
    const sm = new WSStateMachine({
      url: 'wss://example.com/ws',
      heartbeatTimeoutMs: 5000,
      onStateChange: (state) => states.push(state),
    });

    sm.connect();
    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();
    expect(sm.getState()).toBe('CONNECTED');

    // No messages arrive for 6 seconds (exceeding 5000ms heartbeat timeout)
    vi.advanceTimersByTime(6000);

    expect(sm.getState()).toBe('RECONNECTING');
  });

  it('seamlessly updates URL and reconnects if active', () => {
    const sm = new WSStateMachine({ url: 'wss://example.com/stream1' });
    sm.connect();
    const ws1 = MockWebSocket.instances[0];
    ws1.simulateOpen();

    sm.setUrl('wss://example.com/stream2');
    expect(MockWebSocket.instances.length).toBe(2);
    expect(MockWebSocket.instances[1].url).toBe('wss://example.com/stream2');
  });
});
