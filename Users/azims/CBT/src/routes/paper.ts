import { Router, Request, Response } from 'express';
import { prisma } from '../db/prisma';
import { riskGate } from '../middleware/riskGate';
import { defaultRateLimiter } from '../middleware/rateLimit';

const router = Router();

// Apply rate limiting
router.use(defaultRateLimiter);

/**
 * POST /api/paper/trade
 *
 * Places a simulated paper trade, validated through Risk Gate middleware.
 */
router.post('/trade', riskGate, async (req: Request, res: Response): Promise<void> => {
  const { symbol, side, entryPrice, sl, tp, size } = req.body;

  try {
    const trade = await prisma.paperTrade.create({
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

    res.status(201).json({
      message: 'Paper trade executed successfully.',
      trade,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
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
        accountBalance: 100000.0,
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

export default router;
