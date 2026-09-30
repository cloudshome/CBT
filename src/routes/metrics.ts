import { Router, Request, Response } from 'express';
import { prisma } from '../db/prisma';
import { binanceCircuitBreaker, bybitCircuitBreaker } from '../utils/circuitBreaker';

export const metricsRouter = Router();

function stateToNumeric(state: string): number {
  switch (state) {
    case 'CLOSED':
      return 0;
    case 'HALF_OPEN':
      return 1;
    case 'OPEN':
      return 2;
    default:
      return -1;
  }
}

/**
 * GET /metrics — Prometheus standard plaintext metrics exposition endpoint
 */
metricsRouter.get('/metrics', async (_req: Request, res: Response) => {
  const uptime = process.uptime();
  const memory = process.memoryUsage();

  let openTradesCount = 0;
  try {
    openTradesCount = await prisma.paperTrade.count({ where: { status: 'OPEN' } });
  } catch {
    openTradesCount = -1;
  }

  const binanceStatus = binanceCircuitBreaker.getStatus();
  const bybitStatus = bybitCircuitBreaker.getStatus();

  const lines: string[] = [
    '# HELP ctb_node_uptime_seconds Total runtime of the Node.js service in seconds',
    '# TYPE ctb_node_uptime_seconds gauge',
    `ctb_node_uptime_seconds ${uptime.toFixed(2)}`,
    '',
    '# HELP ctb_node_heap_used_bytes Total heap memory in bytes used by the Node process',
    '# TYPE ctb_node_heap_used_bytes gauge',
    `ctb_node_heap_used_bytes ${memory.heapUsed}`,
    '',
    '# HELP ctb_node_rss_bytes Resident Set Size in bytes allocated to the Node process',
    '# TYPE ctb_node_rss_bytes gauge',
    `ctb_node_rss_bytes ${memory.rss}`,
    '',
    '# HELP ctb_exchange_circuit_breaker_state Current state of exchange circuit breakers (0=CLOSED, 1=HALF_OPEN, 2=OPEN)',
    '# TYPE ctb_exchange_circuit_breaker_state gauge',
    `ctb_exchange_circuit_breaker_state{exchange="binance",feed="rest"} ${stateToNumeric(binanceStatus.state)}`,
    `ctb_exchange_circuit_breaker_state{exchange="bybit",feed="rest"} ${stateToNumeric(bybitStatus.state)}`,
    '',
    '# HELP ctb_open_paper_trades_total Current number of active paper trading positions in SQLite',
    '# TYPE ctb_open_paper_trades_total gauge',
    `ctb_open_paper_trades_total ${openTradesCount}`,
    '',
  ];

  res.setHeader('Content-Type', 'text/plain; version=0.0.4; charset=utf-8');
  res.status(200).send(lines.join('\n'));
});

/**
 * GET /api/metrics/json — JSON diagnostic summary
 */
metricsRouter.get('/api/metrics/json', async (_req: Request, res: Response) => {
  const memory = process.memoryUsage();
  let openTradesCount = 0;
  try {
    openTradesCount = await prisma.paperTrade.count({ where: { status: 'OPEN' } });
  } catch {
    openTradesCount = -1;
  }

  res.json({
    uptime_seconds: process.uptime(),
    memory: {
      heap_used_mb: Math.round((memory.heapUsed / 1024 / 1024) * 100) / 100,
      heap_total_mb: Math.round((memory.heapTotal / 1024 / 1024) * 100) / 100,
      rss_mb: Math.round((memory.rss / 1024 / 1024) * 100) / 100,
    },
    circuit_breakers: {
      binance: binanceCircuitBreaker.getStatus(),
      bybit: bybitCircuitBreaker.getStatus(),
    },
    open_paper_trades: openTradesCount,
    timestamp: new Date().toISOString(),
  });
});
