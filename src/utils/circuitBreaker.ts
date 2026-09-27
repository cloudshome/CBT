/**
 * 3-State Resilient Circuit Breaker (CLOSED -> OPEN -> HALF_OPEN).
 *
 * Prevents cascading timeouts and thread exhaustion when external exchange APIs
 * (Binance, Bybit) experience rate limits (HTTP 429), outages, or latency spikes.
 */

export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN';

export interface CircuitBreakerOptions {
  name: string;
  failureThreshold?: number; // Consecutive failures before opening (default: 3)
  cooldownMs?: number;       // Time in ms to remain open before half-open test (default: 30000)
  successThreshold?: number; // Consecutive successes in half-open before closing (default: 2)
}

export class CircuitBreaker {
  public readonly name: string;
  private state: CircuitState = 'CLOSED';
  private failureCount = 0;
  private successCount = 0;
  private nextAttempt = 0;
  private readonly failureThreshold: number;
  private readonly cooldownMs: number;
  private readonly successThreshold: number;

  constructor(options: CircuitBreakerOptions) {
    this.name = options.name;
    this.failureThreshold = options.failureThreshold ?? 3;
    this.cooldownMs = options.cooldownMs ?? 30000;
    this.successThreshold = options.successThreshold ?? 2;
  }

  public getState(): CircuitState {
    if (this.state === 'OPEN' && Date.now() >= this.nextAttempt) {
      this.state = 'HALF_OPEN';
      this.successCount = 0;
    }
    return this.state;
  }

  public isOpen(): boolean {
    return this.getState() === 'OPEN';
  }

  public async execute<T>(action: () => Promise<T>): Promise<T> {
    const currentState = this.getState();

    if (currentState === 'OPEN') {
      throw new Error(`CircuitBreaker[${this.name}] is OPEN. Fast-failing external call.`);
    }

    try {
      const result = await action();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  public onSuccess(): void {
    this.failureCount = 0;
    if (this.state === 'HALF_OPEN') {
      this.successCount += 1;
      if (this.successCount >= this.successThreshold) {
        this.state = 'CLOSED';
        this.successCount = 0;
      }
    } else {
      this.state = 'CLOSED';
    }
  }

  public onFailure(): void {
    this.failureCount += 1;
    if (this.state === 'HALF_OPEN' || this.failureCount >= this.failureThreshold) {
      this.state = 'OPEN';
      this.nextAttempt = Date.now() + this.cooldownMs;
    }
  }

  public reset(): void {
    this.state = 'CLOSED';
    this.failureCount = 0;
    this.successCount = 0;
    this.nextAttempt = 0;
  }

  public getStatus() {
    return {
      name: this.name,
      state: this.getState(),
      failureCount: this.failureCount,
      successCount: this.successCount,
      nextAttempt: this.state === 'OPEN' ? new Date(this.nextAttempt).toISOString() : null,
    };
  }
}

// Dedicated singletons for exchange feeds
export const binanceCircuitBreaker = new CircuitBreaker({ name: 'Binance-REST', failureThreshold: 3, cooldownMs: 30000 });
export const bybitCircuitBreaker = new CircuitBreaker({ name: 'Bybit-REST', failureThreshold: 3, cooldownMs: 30000 });
