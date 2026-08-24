import { Request, Response, NextFunction } from 'express';
import { prisma } from '../db/prisma';

export interface ValidatedTradeData {
  symbol: string;
  side: 'BUY' | 'SELL';
  entryPrice: number;
  sl: number;
  tp: number;
  size: number;
}

/**
 * Risk Gate middleware that validates trade parameters and enforces
 * institutional risk controls (max open trades, max 2% account risk).
 */
export async function riskGate(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  const { symbol, side, entryPrice, sl, tp, size } = req.body;

  // 1. Basic field presence and type validation
  if (!symbol || typeof symbol !== 'string' || symbol.trim() === '') {
    res.status(400).json({ error: 'Field "symbol" is required.' });
    return;
  }

  if (!side || typeof side !== 'string') {
    res.status(400).json({ error: 'Field "side" is required (BUY, SELL, LONG, SHORT).' });
    return;
  }

  const normalizedSide = side.toUpperCase();
  if (!['BUY', 'SELL', 'LONG', 'SHORT'].includes(normalizedSide)) {
    res.status(400).json({ error: 'Invalid side. Allowed values: BUY, SELL, LONG, SHORT.' });
    return;
  }

  const canonicalSide: 'BUY' | 'SELL' =
    normalizedSide === 'BUY' || normalizedSide === 'LONG' ? 'BUY' : 'SELL';

  const entry = Number(entryPrice);
  const stopLoss = Number(sl);
  const takeProfit = Number(tp);
  const positionSize = size !== undefined ? Number(size) : 1.0;

  if (isNaN(entry) || entry <= 0) {
    res.status(400).json({ error: 'Field "entryPrice" must be a positive number.' });
    return;
  }

  if (isNaN(stopLoss) || stopLoss <= 0) {
    res.status(400).json({ error: 'Field "sl" (Stop Loss) must be a positive number.' });
    return;
  }

  if (isNaN(takeProfit) || takeProfit <= 0) {
    res.status(400).json({ error: 'Field "tp" (Take Profit) must be a positive number.' });
    return;
  }

  if (isNaN(positionSize) || positionSize <= 0) {
    res.status(400).json({ error: 'Field "size" must be a positive number.' });
    return;
  }

  // 2. Directional level integrity
  if (canonicalSide === 'BUY') {
    if (stopLoss >= entry || takeProfit <= entry) {
      res.status(400).json({
        error: 'Invalid trade levels for BUY: Stop Loss must be below Entry Price, and Take Profit must be above Entry Price.',
      });
      return;
    }
  } else {
    if (stopLoss <= entry || takeProfit >= entry) {
      res.status(400).json({
        error: 'Invalid trade levels for SELL: Stop Loss must be above Entry Price, and Take Profit must be below Entry Price.',
      });
      return;
    }
  }

  // Normalize symbol (e.g. BTC -> BTCUSDT)
  const cleanSymbol = symbol.trim().toUpperCase();
  const normalizedSymbol = cleanSymbol.endsWith('USDT') ? cleanSymbol : `${cleanSymbol}USDT`;

  try {
    // 3. Retrieve active Risk Configuration (default $100k balance, 3 open trades, 2% risk)
    const config =
      (await prisma.riskConfig.findFirst({ orderBy: { id: 'desc' } })) || {
        accountBalance: 100000.0,
        maxOpenTrades: 3,
        maxRiskPerTrade: 0.02,
        maxDrawdown: 0.1,
        dailyLossLimit: 0.05,
      };

    // 4. Rule 1: Max concurrent open trades limit check
    const currentOpenTrades = await prisma.paperTrade.count({
      where: { status: 'OPEN' },
    });

    if (currentOpenTrades >= config.maxOpenTrades) {
      res.status(403).json({
        error: `Risk Gate Rejection: Maximum open trades limit reached (${config.maxOpenTrades} open trades allowed).`,
        currentOpenTrades,
        maxOpenTrades: config.maxOpenTrades,
      });
      return;
    }

    // 5. Rule 2: Max risk per trade limit check (2% of account balance)
    const dollarRisk = Math.abs(entry - stopLoss) * positionSize;
    const maxAllowedDollarRisk = config.accountBalance * config.maxRiskPerTrade;

    if (dollarRisk > maxAllowedDollarRisk) {
      res.status(403).json({
        error: `Risk Gate Rejection: Trade risk ($${dollarRisk.toFixed(2)}) exceeds maximum allowable risk of ${(config.maxRiskPerTrade * 100).toFixed(0)}% ($${maxAllowedDollarRisk.toFixed(2)}) for account balance $${config.accountBalance.toFixed(2)}.`,
        tradeRisk: dollarRisk,
        maxAllowedRisk: maxAllowedDollarRisk,
        accountBalance: config.accountBalance,
      });
      return;
    }

    // Pass sanitized and validated data
    req.body = {
      symbol: normalizedSymbol,
      side: canonicalSide,
      entryPrice: entry,
      sl: stopLoss,
      tp: takeProfit,
      size: positionSize,
    };

    next();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error('Risk Gate database error:', err);
    res.status(500).json({
      error: 'Internal server error while evaluating risk rules',
      details: msg,
    });
  }
}
