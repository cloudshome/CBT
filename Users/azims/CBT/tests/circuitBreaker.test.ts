import { CircuitBreaker } from '../src/utils/circuitBreaker';

describe('Resilient Circuit Breaker Utility', () => {
  it('should start in CLOSED state and execute successful actions', async () => {
    const cb = new CircuitBreaker({ name: 'Test-CB', failureThreshold: 2, cooldownMs: 1000 });
    expect(cb.getState()).toBe('CLOSED');
    expect(cb.isOpen()).toBe(false);

    const result = await cb.execute(async () => 'OK');
    expect(result).toBe('OK');
    expect(cb.getState()).toBe('CLOSED');
  });

  it('should trip to OPEN after consecutive failures exceed threshold', async () => {
    const cb = new CircuitBreaker({ name: 'Test-CB', failureThreshold: 2, cooldownMs: 500 });

    // 1st failure
    await expect(cb.execute(async () => {
      throw new Error('API Timeout');
    })).rejects.toThrow('API Timeout');
    expect(cb.getState()).toBe('CLOSED');

    // 2nd failure -> Trips to OPEN
    await expect(cb.execute(async () => {
      throw new Error('API 503');
    })).rejects.toThrow('API 503');
    expect(cb.getState()).toBe('OPEN');
    expect(cb.isOpen()).toBe(true);

    // Subsequent calls fast-fail immediately without executing
    let actionExecuted = false;
    await expect(cb.execute(async () => {
      actionExecuted = true;
      return 'UNREACHABLE';
    })).rejects.toThrow('CircuitBreaker[Test-CB] is OPEN. Fast-failing external call.');
    expect(actionExecuted).toBe(false);
  });

  it('should transition to HALF_OPEN after cooldown expires and recover on success', async () => {
    const cb = new CircuitBreaker({ name: 'Test-CB', failureThreshold: 1, cooldownMs: 50, successThreshold: 1 });

    // Trip to OPEN
    await expect(cb.execute(async () => {
      throw new Error('Fail');
    })).rejects.toThrow();
    expect(cb.isOpen()).toBe(true);

    // Wait for cooldown
    await new Promise((resolve) => setTimeout(resolve, 70));

    // Next call transitions to HALF_OPEN and succeeds -> closes circuit
    const res = await cb.execute(async () => 'RECOVERED');
    expect(res).toBe('RECOVERED');
    expect(cb.getState()).toBe('CLOSED');
    expect(cb.isOpen()).toBe(false);
  });
});
