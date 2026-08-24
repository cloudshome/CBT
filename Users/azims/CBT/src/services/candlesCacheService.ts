import { prisma } from '../db/prisma';
import { OHLCVCandle } from '../types/candles';

/**
 * Saves or updates a batch of candles in the SQLite cache
 */
export async function saveCandles(
  symbol: string,
  timeframe: string,
  candles: OHLCVCandle[]
): Promise<void> {
  if (!candles || candles.length === 0) return;

  const operations = candles.map(([ts, o, h, l, c, v]) =>
    prisma.candlesCache.upsert({
      where: {
        symbol_timeframe_ts: {
          symbol,
          timeframe,
          ts: BigInt(ts),
        },
      },
      update: { o, h, l, c, v },
      create: {
        symbol,
        timeframe,
        ts: BigInt(ts),
        o,
        h,
        l,
        c,
        v,
      },
    })
  );

  await prisma.$transaction(operations);
}

/**
 * Retrieves cached candles from SQLite for a given symbol and timeframe,
 * returning up to `limit` candles in ascending chronological order.
 */
export async function getCachedCandles(
  symbol: string,
  timeframe: string,
  limit: number
): Promise<OHLCVCandle[]> {
  const records = await prisma.candlesCache.findMany({
    where: {
      symbol,
      timeframe,
    },
    orderBy: {
      ts: 'desc',
    },
    take: limit,
  });

  // Re-order chronologically (oldest -> newest)
  return records
    .reverse()
    .map((r) => [Number(r.ts), r.o, r.h, r.l, r.c, r.v]);
}
