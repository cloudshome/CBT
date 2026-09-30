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
  // 0. Live Trading Lockout
  // Express backend is strictly a paper-trading simulated path.
  // Live capital execution is outside the Express perimeter and belongs to the certified Python execution vault.
  const rawBodyLive = req.body?.isLiveTrading;
  const rawHeaderLive = req.headers['x-live-trading'];

  const parseLiveFlag = (val: unknown): boolean | 'UNKNOWN' => {
    if (val === undefined || val === null) return false;
    if (typeof val === 'boolean') return val;
    if (typeof val === 'string') {
      const s = val.trim().toLowerCase();
      if (s === 'true') return true;
      if (s === 'false') return false;
      return 'UNKNOWN';
    }
    return 'UNKNOWN';
  };

  const isLiveBody = parseLiveFlag(rawBodyLive);
  const isLiveHeader = parseLiveFlag(rawHeaderLive);

  if (
    isLiveBody === 'UNKNOWN' ||
    isLiveHeader === 'UNKNOWN' ||
    isLiveBody === true ||
    isLiveHeader === true
  ) {
    res.status(403).json({
      error:
        'Risk Gate Rejection: Live trading is strictly prohibited via Express backend. Live capital execution must be routed through the certified Python execution vault (/api/execution).',
    });
    return;
  }

  // 1. Evidence Grade Validation
  // Supported canonical evidence grades: FABRICATED, SIMULATED, IMPUTED, EMPIRICAL
  const CANONICAL_EVIDENCE_GRADES = ['FABRICATED', 'SIMULATED', 'IMPUTED', 'EMPIRICAL'] as const;
  type CanonicalGrade = (typeof CANONICAL_EVIDENCE_GRADES)[number];

  const rawBodyGrade = req.body?.evidenceGrade;
  const rawHeaderGrade = req.headers['x-evidence-grade'];

  const normalizeGrade = (val: unknown): string | null => {
    if (val === undefined || val === null) return null;
    if (typeof val === 'string') {
      const trimmed = val.trim().toUpperCase();
      return trimmed.length > 0 ? trimmed : null;
    }
    return 'UNKNOWN_TYPE';
  };

  const bodyGrade = normalizeGrade(rawBodyGrade);
  const headerGrade = normalizeGrade(rawHeaderGrade);

  let resolvedGrade: string;

  if (bodyGrade !== null && headerGrade !== null) {
    // Both supplied: normalize both. If they disagree -> HTTP 403
    if (bodyGrade !== headerGrade) {
      res.status(403).json({
        error: `Risk Gate Rejection: Conflicting evidence grades supplied in body ('${bodyGrade}') and header ('${headerGrade}'). Disagreement fails closed.`,
      });
      return;
    }
    resolvedGrade = bodyGrade;
  } else if (bodyGrade !== null) {
    resolvedGrade = bodyGrade;
  } else if (headerGrade !== null) {
    resolvedGrade = headerGrade;
  } else {
    // Neither supplied -> preserve established paper-mode compatibility behavior (missing -> EMPIRICAL)
    resolvedGrade = 'EMPIRICAL';
  }

  // Unknown/unrecognized evidence grades MUST NOT default to EMPIRICAL; fail closed with 403
  if (!CANONICAL_EVIDENCE_GRADES.includes(resolvedGrade as CanonicalGrade)) {
    res.status(403).json({
      error: `Risk Gate Rejection: Unknown or invalid evidence grade '${resolvedGrade}'. Must be one of: ${CANONICAL_EVIDENCE_GRADES.join(', ')}.`,
    });
    return;
  }

  // Enforce evidence integrity: Only EMPIRICAL may pass this boundary
  if (resolvedGrade !== 'EMPIRICAL') {
    res.status(403).json({
      error: `Risk Gate Rejection: Evidence grade '${resolvedGrade}' is non-empirical and cannot authorize trade sizing. Only EMPIRICAL evidence is tradeable.`,
      evidenceGrade: resolvedGrade,
    });
    return;
  }

  const { symbol, side, entryPrice, sl, tp, size } = req.body || {};

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
    // 3. Retrieve active Risk Configuration (default $10k balance, 3 open trades, 2% risk)
    const config =
      (await prisma.riskConfig.findFirst({ orderBy: { id: 'desc' } })) || {
        accountBalance: 10000.0,
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

    // 6. Rule 3: Daily realized loss limit check (5% of account balance)
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const closedToday = await prisma.paperTrade.findMany({
      where: {
        status: 'CLOSED',
        closedAt: { gte: today },
      },
    });
    const dailyPnL = closedToday.reduce(
      (acc: number, trade: { pnl: number | null }) => acc + (trade.pnl || 0),
      0
    );
    const maxDailyLoss = config.accountBalance * (config.dailyLossLimit || 0.05);

    if (dailyPnL <= -maxDailyLoss) {
      res.status(403).json({
        error: `Risk Gate Rejection: Daily loss limit reached ($${Math.abs(dailyPnL).toFixed(2)} lost today >= max allowed $${maxDailyLoss.toFixed(2)}). All new entries locked until 00:00 UTC.`,
        dailyPnL,
        maxDailyLoss,
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
