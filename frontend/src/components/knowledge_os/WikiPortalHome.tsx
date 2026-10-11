import React from 'react';
import {
  Sparkles,
  TrendingUp,
  History,
  HelpCircle,
  BookOpen,
  ArrowRight,
  Compass,
} from 'lucide-react';
import { WikiArticleSummary } from '../../types';

interface WikiPortalHomeProps {
  articles: WikiArticleSummary[];
  onSelectArticle: (articleId: string) => void;
  onOpenWebSearch?: () => void;
  onExploreCategory?: (category: string) => void;
}

export const WikiPortalHome: React.FC<WikiPortalHomeProps> = ({
  articles,
  onSelectArticle,
  onOpenWebSearch,
  onExploreCategory,
}) => {
  // Select featured article: highest verification score, or fallback to first
  const featuredArticle =
    articles.find((a) => a.article_id.includes('concentrated_liquidity')) ||
    articles.find((a) => a.verification_score >= 95) ||
    articles[0];

  // News items: 4 most recent articles
  const newsArticles = articles
    .filter((a) => a.article_id !== featuredArticle?.article_id)
    .slice(0, 4);

  // Formatted date string for today
  const todayStr = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto w-full space-y-6 font-sans text-[#202122] dark:text-[#eaecf0]">
      {/* 1. Wikipedia Welcome Header Banner */}
      <div className="border border-[#a2a9b1] dark:border-[#2d3a4e] bg-[#f8f9fa] dark:bg-[#131b27] p-4 sm:p-5 rounded shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-mono text-[#54595d] dark:text-slate-400 mb-0.5">
              Edition: Institutional Quantitative Terminal • {todayStr}
            </div>
            <h1 className="text-xl sm:text-2xl font-serif font-bold text-[#101418] dark:text-white">
              Welcome to <span className="text-[#3366cc] dark:text-blue-400">SKY Research Wikipedia</span>
            </h1>
            <p className="text-xs text-[#54595d] dark:text-[#9aa0a6] mt-1 font-sans">
              The free, autonomous quantitative knowledge encyclopedia that anyone can verify.
            </p>
          </div>
          <div className="flex items-center gap-3 self-start md:self-auto">
            <div className="px-3 py-1.5 rounded bg-white dark:bg-[#1a2332] border border-[#c8ccd1] dark:border-[#38455c] text-center shadow-xs">
              <span className="block text-xs font-mono font-bold text-[#3366cc] dark:text-blue-400">
                {articles.length}
              </span>
              <span className="text-[10px] text-[#54595d] dark:text-slate-400 font-sans uppercase tracking-wider">
                Articles Stored
              </span>
            </div>
            <div className="px-3 py-1.5 rounded bg-[#e6f4ea] dark:bg-emerald-950/40 border border-[#ceead6] dark:border-emerald-800/50 text-center shadow-xs">
              <span className="block text-xs font-mono font-bold text-[#137333] dark:text-emerald-400">
                100% Causal
              </span>
              <span className="text-[10px] text-[#137333]/80 dark:text-emerald-500 font-sans uppercase tracking-wider">
                Firewalled
              </span>
            </div>
          </div>
        </div>

        {/* Portal Category Navigation Strip */}
        <div className="mt-4 pt-3 border-t border-[#eaecf0] dark:border-[#243042] flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold text-[#54595d] dark:text-slate-400 text-[11px] uppercase tracking-wider mr-1">
            Portals:
          </span>
          {[
            'Macro Geopolitics & Hegemony',
            'Monetary Policy & Debt Cycles',
            'Quantitative Market Structure',
            'Crypto & Decentralized Settlement',
          ].map((cat) => (
            <button
              key={cat}
              onClick={() => onExploreCategory && onExploreCategory(cat)}
              className="px-2.5 py-1 rounded-full bg-white dark:bg-[#1b2535] hover:bg-[#eaecf0] dark:hover:bg-[#253349] border border-[#c8ccd1] dark:border-[#34445c] text-[#3366cc] dark:text-blue-300 text-[11px] font-medium transition cursor-pointer"
            >
              {cat}
            </button>
          ))}
          {onOpenWebSearch && (
            <button
              onClick={onOpenWebSearch}
              className="ml-auto inline-flex items-center gap-1.5 px-3 py-1 rounded bg-[#3366cc] hover:bg-[#2a4b8d] text-white text-[11px] font-medium transition cursor-pointer"
            >
              <Compass size={12} />
              <span>Explore Live Web</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. Main Dual-Column Grid (Wikipedia Front Page Layout) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* LEFT COLUMN: Featured Article & Did You Know (7 Cols) */}
        <div className="lg:col-span-7 space-y-5">
          {/* Section: From Today's Featured Article */}
          <div className="border border-[#a2a9b1] dark:border-[#2d3a4e] rounded bg-white dark:bg-[#0f141f] shadow-xs overflow-hidden">
            <div className="bg-[#eaecf0] dark:bg-[#1b2535] px-4 py-2 border-b border-[#a2a9b1] dark:border-[#2d3a4e] flex items-center justify-between">
              <h2 className="font-serif font-bold text-sm text-[#101418] dark:text-white flex items-center gap-1.5">
                <Sparkles size={15} className="text-[#3366cc] dark:text-blue-400" />
                <span>From today&apos;s featured article</span>
              </h2>
              <span className="text-[10px] font-mono text-[#54595d] dark:text-slate-400">
                Peer-Reviewed • {featuredArticle ? `${featuredArticle.verification_score.toFixed(0)}% Rigor` : 'Verified'}
              </span>
            </div>

            <div className="p-4 sm:p-5 space-y-3">
              {featuredArticle ? (
                <>
                  <div className="flex items-start justify-between gap-3">
                    <h3
                      onClick={() => onSelectArticle(featuredArticle.article_id)}
                      className="text-base sm:text-lg font-serif font-bold text-[#0b0080] dark:text-blue-300 hover:underline cursor-pointer leading-tight"
                    >
                      {featuredArticle.title}
                    </h3>
                  </div>

                  <div className="text-xs text-[#54595d] dark:text-[#9aa0a6] font-mono flex items-center gap-2">
                    <span>Category: {featuredArticle.category}</span>
                    <span>•</span>
                    <span>By: {featuredArticle.author_or_speaker || 'Quantitative Researcher'}</span>
                  </div>

                  <p className="text-xs sm:text-sm text-[#202122] dark:text-slate-200 leading-relaxed font-serif">
                    {featuredArticle.executive_summary}
                  </p>

                  {/* Highlights / Wikilinks */}
                  {featuredArticle.wikilinks && featuredArticle.wikilinks.length > 0 && (
                    <div className="pt-2 flex flex-wrap gap-1.5">
                      {featuredArticle.wikilinks.slice(0, 5).map((wl) => (
                        <span
                          key={wl}
                          className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#f0f4f8] dark:bg-[#192434] text-[#3366cc] dark:text-blue-300 border border-[#d0d7de] dark:border-[#2c3d55]"
                        >
                          [[{wl}]]
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="pt-3 border-t border-[#eaecf0] dark:border-[#202c3e] flex items-center justify-between">
                    <button
                      onClick={() => onSelectArticle(featuredArticle.article_id)}
                      className="text-xs font-sans font-bold text-[#3366cc] dark:text-blue-400 hover:underline flex items-center gap-1 cursor-pointer"
                    >
                      <span>Read full encyclopedia article...</span>
                      <ArrowRight size={13} />
                    </button>
                    <span className="text-[10px] font-mono text-[#72777d] dark:text-slate-500">
                      ID: {featuredArticle.article_id}
                    </span>
                  </div>
                </>
              ) : (
                <div className="text-xs text-[#54595d] dark:text-slate-400 py-4 text-center">
                  No featured article available yet. Ingest articles or crawl the web to populate!
                </div>
              )}
            </div>
          </div>

          {/* Section: Did You Know (Empirical Quant Insights) */}
          <div className="border border-[#a2a9b1] dark:border-[#2d3a4e] rounded bg-white dark:bg-[#0f141f] shadow-xs overflow-hidden">
            <div className="bg-[#eaecf0] dark:bg-[#1b2535] px-4 py-2 border-b border-[#a2a9b1] dark:border-[#2d3a4e]">
              <h2 className="font-serif font-bold text-sm text-[#101418] dark:text-white flex items-center gap-1.5">
                <HelpCircle size={15} className="text-[#137333] dark:text-emerald-400" />
                <span>Did you know ...</span>
              </h2>
            </div>
            <div className="p-4 sm:p-5 space-y-2.5 text-xs text-[#202122] dark:text-slate-200 leading-relaxed font-sans">
              <div className="flex items-start gap-2">
                <span className="text-[#3366cc] dark:text-blue-400 font-bold">•</span>
                <p>
                  ... that under <span className="text-[#0b0080] dark:text-blue-300 font-semibold">Half-Kelly Sizing</span>, risking half of the optimal geometric growth rate reduces account drawdown probability by <span className="font-bold">75%</span> with only a 25% penalty to long-term compound growth?
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-[#3366cc] dark:text-blue-400 font-bold">•</span>
                <p>
                  ... that in concentrated liquidity AMMs (Uniswap v3/v4), liquidity providers experience <span className="text-[#0b0080] dark:text-blue-300 font-semibold">Loss Versus Rebalancing (LVR)</span> as an irreversible structural cost paid to arbitrageurs running latency-advantaged MEV?
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-[#3366cc] dark:text-blue-400 font-bold">•</span>
                <p>
                  ... that institutional order book <span className="text-[#0b0080] dark:text-blue-300 font-semibold">Order Flow Imbalance (OFI)</span> and VPIN metrics predict short-term directional toxicity up to 600 milliseconds before major price breaks occur?
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-[#3366cc] dark:text-blue-400 font-bold">•</span>
                <p>
                  ... that the CBT causal firewall enforces a <span className="text-[#0b0080] dark:text-blue-300 font-semibold">Zero-Lookahead convention</span> where no empirical fact is permitted into an agent thesis unless its timestamp strictly precedes bar-close?
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: In The News & On This Day (5 Cols) */}
        <div className="lg:col-span-5 space-y-5">
          {/* Section: In The News / Protocol Releases */}
          <div className="border border-[#a2a9b1] dark:border-[#2d3a4e] rounded bg-white dark:bg-[#0f141f] shadow-xs overflow-hidden">
            <div className="bg-[#eaecf0] dark:bg-[#1b2535] px-4 py-2 border-b border-[#a2a9b1] dark:border-[#2d3a4e] flex items-center justify-between">
              <h2 className="font-serif font-bold text-sm text-[#101418] dark:text-white flex items-center gap-1.5">
                <TrendingUp size={15} className="text-[#b06000] dark:text-amber-400" />
                <span>In the news & protocol releases</span>
              </h2>
              <span className="text-[10px] font-mono text-[#54595d] dark:text-slate-400">
                Auto-Crawled Feeds
              </span>
            </div>

            <div className="p-4 space-y-3">
              {newsArticles.length > 0 ? (
                newsArticles.map((item) => (
                  <div
                    key={item.article_id}
                    onClick={() => onSelectArticle(item.article_id)}
                    className="p-2.5 rounded hover:bg-[#f8f9fa] dark:hover:bg-[#16202f] border border-transparent hover:border-[#c8ccd1] dark:hover:border-[#2b3a50] transition cursor-pointer space-y-1"
                  >
                    <div className="flex items-center justify-between text-[10px] text-[#54595d] dark:text-slate-400 font-mono">
                      <span>{item.author_or_speaker || item.source_type}</span>
                      <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                        {item.verification_score.toFixed(0)}% Rigor
                      </span>
                    </div>
                    <h4 className="text-xs font-serif font-bold text-[#0b0080] dark:text-blue-300 line-clamp-2">
                      {item.title}
                    </h4>
                    <p className="text-[11px] text-[#54595d] dark:text-slate-400 line-clamp-2 leading-relaxed">
                      {item.executive_summary}
                    </p>
                  </div>
                ))
              ) : (
                <div className="text-xs text-[#54595d] dark:text-slate-400 text-center py-4">
                  No news items loaded.
                </div>
              )}
            </div>
          </div>

          {/* Section: On This Day in Macro & Crypto History */}
          <div className="border border-[#a2a9b1] dark:border-[#2d3a4e] rounded bg-white dark:bg-[#0f141f] shadow-xs overflow-hidden">
            <div className="bg-[#eaecf0] dark:bg-[#1b2535] px-4 py-2 border-b border-[#a2a9b1] dark:border-[#2d3a4e]">
              <h2 className="font-serif font-bold text-sm text-[#101418] dark:text-white flex items-center gap-1.5">
                <History size={15} className="text-[#6554c0] dark:text-purple-400" />
                <span>On this day in Macro & Crypto History</span>
              </h2>
            </div>
            <div className="p-4 space-y-3 text-xs text-[#202122] dark:text-slate-200 leading-relaxed font-sans">
              <div className="border-b border-[#eaecf0] dark:border-[#202c3e] pb-2">
                <span className="font-mono font-bold text-[#0b0080] dark:text-blue-300">2009:</span>{' '}
                Satoshi Nakamoto mines the Bitcoin Genesis Block (Block 0) embedding the Times headline:{' '}
                <em className="text-[#54595d] dark:text-slate-400">
                  &ldquo;Chancellor on brink of second bailout for banks&rdquo;
                </em>.
              </div>
              <div className="border-b border-[#eaecf0] dark:border-[#202c3e] pb-2">
                <span className="font-mono font-bold text-[#0b0080] dark:text-blue-300">1985:</span>{' '}
                The G5 nations sign the <span className="font-semibold">Plaza Accord</span> to depreciate the US dollar relative to the Japanese Yen and German Deutsche Mark.
              </div>
              <div className="border-b border-[#eaecf0] dark:border-[#202c3e] pb-2">
                <span className="font-mono font-bold text-[#0b0080] dark:text-blue-300">1971:</span>{' '}
                President Richard Nixon suspends the dollar&apos;s convertibility into gold, terminating the Bretton Woods fixed exchange rate framework.
              </div>
              <div>
                <span className="font-mono font-bold text-[#0b0080] dark:text-blue-300">2020:</span>{' '}
                The &ldquo;Black Thursday&rdquo; liquidity cascade sees BTC drop 50% in 24 hours as Ethereum gas prices exceed 400 gwei, triggering cascading liquidations across MakerDAO.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Bottom Strip: Today's Featured Chart & Mathematical Formulation */}
      <div className="border border-[#a2a9b1] dark:border-[#2d3a4e] rounded bg-white dark:bg-[#0f141f] p-4 sm:p-5 shadow-xs">
        <h2 className="font-serif font-bold text-sm text-[#101418] dark:text-white flex items-center gap-1.5 mb-2">
          <BookOpen size={15} className="text-[#3366cc] dark:text-blue-400" />
          <span>Today&apos;s Featured Quantitative Concept</span>
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="bg-[#f8f9fa] dark:bg-[#141d2a] p-3 rounded border border-[#c8ccd1] dark:border-[#2a384e]">
            <h4 className="font-mono font-bold text-[#0b0080] dark:text-blue-300 mb-1">
              Half-Kelly Fraction
            </h4>
            <code className="block bg-white dark:bg-[#0b1017] p-2 rounded text-[11px] font-mono text-[#137333] dark:text-emerald-400 mb-1 border border-[#eaecf0] dark:border-[#1e2a3c]">
              f* = 0.5 &times; (p/a - q/b)
            </code>
            <p className="text-[11px] text-[#54595d] dark:text-slate-400">
              Guarantees zero-ruin trajectory under parameter estimation uncertainty and leptokurtic crypto fat tails.
            </p>
          </div>

          <div className="bg-[#f8f9fa] dark:bg-[#141d2a] p-3 rounded border border-[#c8ccd1] dark:border-[#2a384e]">
            <h4 className="font-mono font-bold text-[#0b0080] dark:text-blue-300 mb-1">
              Order Flow Imbalance (OFI)
            </h4>
            <code className="block bg-white dark:bg-[#0b1017] p-2 rounded text-[11px] font-mono text-[#137333] dark:text-emerald-400 mb-1 border border-[#eaecf0] dark:border-[#1e2a3c]">
              OFI_t = &Delta;V_bid(t) - &Delta;V_ask(t)
            </code>
            <p className="text-[11px] text-[#54595d] dark:text-slate-400">
              Quantifies instantaneous net limit order flow pressure before execution at best bid and ask quotes.
            </p>
          </div>

          <div className="bg-[#f8f9fa] dark:bg-[#141d2a] p-3 rounded border border-[#c8ccd1] dark:border-[#2a384e]">
            <h4 className="font-mono font-bold text-[#0b0080] dark:text-blue-300 mb-1">
              Deflated Sharpe Ratio (DSR)
            </h4>
            <code className="block bg-white dark:bg-[#0b1017] p-2 rounded text-[11px] font-mono text-[#137333] dark:text-emerald-400 mb-1 border border-[#eaecf0] dark:border-[#1e2a3c]">
              DSR = &Phi;((SR - SR_0) / &sigma;_SR)
            </code>
            <p className="text-[11px] text-[#54595d] dark:text-slate-400">
              Penalizes selection bias across multiple hypothesis trials to prevent false discoveries in strategy backtests.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
