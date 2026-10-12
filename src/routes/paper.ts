import { Router, Request, Response } from 'express';
import { prisma } from '../db/prisma';
import { riskGate } from '../middleware/riskGate';
import { defaultRateLimiter } from '../middleware/rateLimit';

const router = Router();

// Apply rate limiting
router.use(defaultRateLimiter);

// Institutional governance header: flag legacy Express fallback
router.use((_req: Request, res: Response, next) => {
  res.setHeader('X-Legacy-Fallback', 'true');
  res.setHeader('X-Authoritative-Paper-Service', 'FastAPI:8000');
  next();
});

/**
 * POST /api/paper/trade
 *
 * Places a simulated paper trade, validated through Risk Gate middleware.
 * Enforces atomic execution inside a Prisma transaction to eliminate race conditions.
 */
router.post('/trade', riskGate, async (req: Request, res: Response): Promise<void> => {
  const { symbol, side, entryPrice, sl, tp, size } = req.body;

  try {
    const trade = await prisma.$transaction(async (tx) => {
      // Re-verify open trades limit inside transaction to prevent concurrent race condition
      const riskConfig = (await tx.riskConfig.findFirst()) || { maxOpenTrades: 3 };
      const currentOpenTrades = await tx.paperTrade.count({
        where: { status: 'OPEN' },
      });

      if (currentOpenTrades >= riskConfig.maxOpenTrades) {
        throw new Error(`CONCURRENCY_LIMIT_EXCEEDED:${riskConfig.maxOpenTrades}:${currentOpenTrades}`);
      }

      return await tx.paperTrade.create({
        data: {
          symbol,
          side,
          entryPrice,
          sl,
          tp,
          size,
          status: 'OPEN',
        },
      });
    });

    res.status(201).json({
      message: 'Paper trade executed successfully.',
      trade,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.startsWith('CONCURRENCY_LIMIT_EXCEEDED:')) {
      const parts = msg.split(':');
      const maxTrades = Number(parts[1]);
      const openTrades = Number(parts[2]);
      res.status(403).json({
        error: `Risk Gate Rejection: Maximum open trades limit reached (${maxTrades} open trades allowed).`,
        currentOpenTrades: openTrades,
        maxOpenTrades: maxTrades,
      });
      return;
    }

    console.error('Error creating paper trade:', err);
    res.status(500).json({
      error: 'Failed to create paper trade record.',
      details: msg,
    });
  }
});

/**
 * GET /api/paper/positions
 *
 * Retrieves all currently open paper trading positions.
 */
router.get('/positions', async (_req: Request, res: Response): Promise<void> => {
  try {
    const positions = await prisma.paperTrade.findMany({
      where: { status: 'OPEN' },
      orderBy: { createdAt: 'desc' },
    });

    res.json({
      positions,
      count: positions.length,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error('Error fetching paper positions:', err);
    res.status(500).json({
      error: 'Failed to retrieve paper positions.',
      details: msg,
    });
  }
});

/**
 * GET /api/paper/config
 *
 * Retrieves the current risk configuration and account balance.
 */
router.get('/config', async (_req: Request, res: Response): Promise<void> => {
  try {
    const config =
      (await prisma.riskConfig.findFirst({ orderBy: { id: 'desc' } })) || {
        accountBalance: 10000.0,
        maxDrawdown: 0.1,
        maxOpenTrades: 3,
        dailyLossLimit: 0.05,
        maxRiskPerTrade: 0.02,
      };

    res.json({ config });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(500).json({
      error: 'Failed to retrieve risk config.',
      details: msg,
    });
  }
});

/**
 * POST /api/paper/reconcile
 *
 * Reconciles open positions against provided current prices, auto-closing triggered TP/SL.
 */
router.post('/reconcile', async (req: Request, res: Response): Promise<void> => {
  const { prices } = req.body;
  if (!prices || typeof prices !== 'object') {
    res.status(400).json({ error: 'Missing or invalid prices object in request body.' });
    return;
  }

  try {
    const { reconcileOpenPositions } = await import('../services/reconciliationService');
    const result = await reconcileOpenPositions(prices);
    res.json({
      message: `Reconciliation complete. Closed ${result.closedCount} positions.`,
      result,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(500).json({
      error: 'Failed to reconcile paper positions.',
      details: msg,
    });
  }
});

export default router;
