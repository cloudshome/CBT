import { prisma } from '../db/prisma';

export interface ReconcileResult {
  closedCount: number;
  closedTrades: Array<{
    id: number;
    symbol: string;
    reason: 'TAKE_PROFIT' | 'STOP_LOSS';
    exitPrice: number;
    pnl: number;
  }>;
}

/**
 * Reconciles open paper trades against current market prices.
 * Automatically closes positions that hit Take-Profit or Stop-Loss boundaries.
 */
export async function reconcileOpenPositions(currentPrices: Record<string, number>): Promise<ReconcileResult> {
  const openTrades = await prisma.paperTrade.findMany({
    where: { status: 'OPEN' },
  });

  const closedTrades: ReconcileResult['closedTrades'] = [];

  for (const trade of openTrades) {
    const currentPrice = currentPrices[trade.symbol];
    if (typeof currentPrice !== 'number' || isNaN(currentPrice) || currentPrice <= 0) {
      continue;
    }

    let shouldClose = false;
    let reason: 'TAKE_PROFIT' | 'STOP_LOSS' = 'TAKE_PROFIT';

    const sideUpper = trade.side.toUpperCase();
    const isLong = sideUpper === 'LONG' || sideUpper === 'BUY';

    if (isLong) {
      if (trade.tp && currentPrice >= trade.tp) {
        shouldClose = true;
        reason = 'TAKE_PROFIT';
      } else if (trade.sl && currentPrice <= trade.sl) {
        shouldClose = true;
        reason = 'STOP_LOSS';
      }
    } else {
      if (trade.tp && currentPrice <= trade.tp) {
        shouldClose = true;
        reason = 'TAKE_PROFIT';
      } else if (trade.sl && currentPrice >= trade.sl) {
        shouldClose = true;
        reason = 'STOP_LOSS';
      }
    }

    if (shouldClose) {
      const pnl = isLong
        ? (currentPrice - trade.entryPrice) * trade.size
        : (trade.entryPrice - currentPrice) * trade.size;

      await prisma.paperTrade.update({
        where: { id: trade.id },
        data: {
          status: 'CLOSED',
          exitPrice: currentPrice,
          pnl: Math.round(pnl * 100) / 100,
          closedAt: new Date(),
        },
      });

      closedTrades.push({
        id: trade.id,
        symbol: trade.symbol,
        reason,
        exitPrice: currentPrice,
        pnl: Math.round(pnl * 100) / 100,
      });
    }
  }

  return {
    closedCount: closedTrades.length,
    closedTrades,
  };
}
