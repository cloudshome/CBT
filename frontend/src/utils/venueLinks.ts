/**
 * venueLinks.ts
 * =============
 * Authoritative client-side utility for constructing institutional deep-links
 * to TradingView (Futures .P & Spot), Binance (Futures & Spot), and Bybit.
 */

export function cleanSymbol(symbol: string): string {
  if (!symbol) return 'BTCUSDT';
  return symbol.replace(/[^A-Z0-9]/gi, '').toUpperCase();
}

export function getBaseAsset(symbol: string): string {
  const clean = cleanSymbol(symbol);
  if (clean.endsWith('USDT')) return clean.slice(0, -4);
  if (clean.endsWith('BUSD')) return clean.slice(0, -4);
  if (clean.endsWith('USDC')) return clean.slice(0, -4);
  return clean;
}

export function buildTradingViewUrl(symbol: string, isFutures: boolean = true): string {
  const clean = cleanSymbol(symbol);
  if (clean === 'XAUUSDT' || clean === 'XAUUSD' || clean.includes('GOLD')) {
    return 'https://www.tradingview.com/chart/?symbol=OANDA:XAUUSD';
  }
  if (clean.includes('PAXG')) {
    return 'https://www.tradingview.com/chart/?symbol=BINANCE:PAXGUSDT';
  }
  const suffix = isFutures ? '.P' : '';
  return `https://www.tradingview.com/chart/?symbol=BINANCE:${clean}${suffix}`;
}

export function buildBinanceUrl(symbol: string, isFutures: boolean = true): string {
  const clean = cleanSymbol(symbol);
  const base = getBaseAsset(symbol);
  if (clean === 'XAUUSDT' || clean === 'XAUUSD') {
    return 'https://www.binance.com/en/futures/PAXGUSDT';
  }
  if (clean.includes('PAXG')) {
    return 'https://www.binance.com/en/trade/PAXG_USDT';
  }
  if (isFutures) {
    return `https://www.binance.com/en/futures/${base}USDT`;
  }
  return `https://www.binance.com/en/trade/${base}_USDT`;
}

export function buildBybitUrl(symbol: string): string {
  const clean = cleanSymbol(symbol);
  const base = getBaseAsset(symbol);
  if (clean.includes('PAXG')) {
    return 'https://www.bybit.com/trade/spot/PAXG/USDT';
  }
  return `https://www.bybit.com/trade/usdt/${base}USDT`;
}

