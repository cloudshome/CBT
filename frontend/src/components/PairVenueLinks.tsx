import React from 'react';
import { ExternalLink, Crosshair } from 'lucide-react';
import { buildTradingViewUrl, buildBinanceUrl, buildBybitUrl, cleanSymbol } from '../utils/venueLinks';

interface PairVenueLinksProps {
  symbol: string;
  isFutures?: boolean;
  size?: 'xs' | 'sm';
  showCockpitSelect?: boolean;
  onSelectSymbol?: (symbol: string) => void;
  className?: string;
}

export const PairVenueLinks: React.FC<PairVenueLinksProps> = ({
  symbol,
  isFutures = true,
  size = 'xs',
  showCockpitSelect = false,
  onSelectSymbol,
  className = '',
}) => {
  const tvUrl = buildTradingViewUrl(symbol, isFutures);
  const binanceUrl = buildBinanceUrl(symbol, isFutures);
  const bybitUrl = buildBybitUrl(symbol);
  const clean = cleanSymbol(symbol);

  const btnPadding = size === 'xs' ? 'px-1 py-0.5 text-[9px]' : 'px-1.5 py-0.5 text-[10px]';
  const iconSize = size === 'xs' ? 9 : 11;

  return (
    <div className={`inline-flex items-center gap-1 font-mono ${className}`}>
      {showCockpitSelect && onSelectSymbol && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onSelectSymbol(clean);
          }}
          className={`${btnPadding} bg-cyan-950/80 hover:bg-cyan-500/20 text-cyan-300 hover:text-cyan-200 border border-cyan-800/60 rounded flex items-center gap-0.5 font-bold transition-all shadow-sm`}
          title={`Load ${symbol} into CBT Cockpit Terminal`}
        >
          <Crosshair size={iconSize} />
          <span>Chart</span>
        </button>
      )}

      {/* TradingView Link */}
      <a
        href={tvUrl}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        className={`${btnPadding} bg-slate-800/90 hover:bg-cyan-500/20 text-slate-300 hover:text-cyan-300 border border-slate-700/80 rounded flex items-center gap-0.5 font-bold transition-all shadow-sm`}
        title={`Open ${symbol} on TradingView (${isFutures ? 'Perpetual Futures .P' : 'Spot'})`}
      >
        <ExternalLink size={iconSize} className="opacity-70" />
        <span>TV</span>
      </a>

      {/* Binance Link */}
      <a
        href={binanceUrl}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        className={`${btnPadding} bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded flex items-center gap-0.5 font-bold transition-all shadow-sm`}
        title={`Trade ${symbol} on Binance (${isFutures ? 'Futures' : 'Spot'})`}
      >
        <span>BINANCE</span>
      </a>

      {/* Bybit Link */}
      <a
        href={bybitUrl}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        className={`${btnPadding} bg-orange-500/10 hover:bg-orange-500/20 text-orange-300 border border-orange-500/30 rounded flex items-center gap-0.5 font-bold transition-all shadow-sm`}
        title={`Trade ${symbol} on Bybit Perpetual`}
      >
        <span>BYBIT</span>
      </a>
    </div>
  );
};

