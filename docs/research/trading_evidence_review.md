# Empirical Trading Evidence Review & Research Priority Ranking

**Document Version:** `1.0.0`  
**Date:** 2026-10-13  
**Scope:** Primary empirical literature, institutional derivatives research, and CBT/SKY repository replication evidence across 10 core quantitative & discretionary domains for `BTCUSDT` and `ETHUSDT` futures.

> **Epistemic Discipline:** Every finding below distinguishes between `[FACT]` (peer-reviewed empirical result or verified CBT real-data backtest), `[INFERENCE]` (structural transferability to BTC/ETH futures), and `[HYPOTHESIS]` (unvalidated discretionary or microstructure claim). We explicitly separate **equities vs. futures vs. crypto**, **long-horizon vs. intraday**, **gross vs. net returns**, **observed correlation vs. out-of-sample predictive value**, and **statistical significance vs. practical tradability**.

---

## 1. Domain-by-Domain Empirical Evidence Synthesis

### 1.1 Time-Series Momentum (TSMOM) & Diversified Trend Following
- **Primary Sources:**
  - Moskowitz, Ooi & Pedersen (2012), *"Time Series Momentum"*, *Journal of Financial Economics*, 104(2), 228–250 (58 liquid futures across equity indices, currencies, commodities, and bonds, 1965–2009, 1m–12m horizons).
  - Hurst, Ooi & Pedersen (2017), *"A Century of Evidence on Trend-Following Investing"*, *Journal of Portfolio Management*, 44(1), 15–29 (1880–2016).
  - Liu & Tsyvinski (2021), *"Risks and Returns of Cryptocurrency"*, *Review of Financial Studies*, 34(6), 2689–2727 (BTC, ETH, XRP; 1-week to 8-week time-series momentum, 2011–2018).
  - Fiebig,isl &齐 / Dobrynskaya (2021–2023), crypto trend-following replications on `BTC` and `ETH` (`4h` and `1d` horizons).
- **Asset Class & Horizon Distinction:**
  - **Equities/Futures vs. Crypto:** In traditional futures, TSMOM peaks at 3-to-12-month lookbacks. In cryptocurrency (`BTC`, `ETH`), information diffusion and retail attention cycles operate faster: empirical momentum is strongest at **7-day to 30-day lookbacks on `4h` and `1d` bars** (`[FACT]`). On intraday horizons (`5m`, `15m`), pure TSMOM degrades sharply due to microstructure noise and taker fees (`[FACT]` — verified in CBT's 2026-08-14 real BTCUSDT 15m run where 1h horizon lost `-0.452R`).
- **Gross vs. Net & Tradability:**
  - Because `4h`/`1d` TSMOM holds positions for days to weeks (low turnover, ~25–60 round-trips/year), round-trip perp fees (`~10–15 bps`) consume less than $10\%$ of gross edge. However, **long-side funding drag** during bull markets (`+10%` to `+40%` annualized) can erode 30–50% of gross trend returns unless filtered by funding extremes (`TC_039`).

---

### 1.2 Cross-Sectional Crypto Momentum & Relative-Strength Rotation
- **Primary Sources:**
  - Jegadeesh & Titman (1993), *"Returns to Buying Winners and Selling Losers"*, *Journal of Finance*, 48(1), 65–91 (US Equities, 1965–1989).
  - Liu, Tsyvinski & Wu (2022), *"Common Risk Factors in Cryptocurrency"*, *Journal of Finance*, 77(2), 1133–1177 (1,800+ coins, 2014–2020; 1–4 week cross-sectional momentum factor `CMOM`).
  - Asness, Moskowitz & Pedersen (2013), *"Value and Momentum Everywhere"*, *Journal of Finance*, 68(3), 929–985.
- **Asset Class & Horizon Distinction:**
  - Cross-sectional momentum (`TC_035`) is statistically significant ($t > 3.0$ gross) across the top 20–50 liquid cryptocurrencies at 1-to-3-week horizons (`[FACT]`).
  - **Relevance to BTC/ETH Futures:** When the trading universe is strictly restricted to **two primary assets (`BTC` and `ETH`)**, full cross-sectional long-short decile portfolios cannot be formed. Instead, cross-sectional momentum collapses into **Relative-Strength Rotation (`TC_036`)** — dynamically overweighting `BTC` vs. `ETH` based on rolling `ETH/BTC` momentum and volatility-adjusted trend strength (`[INFERENCE]`).

---

### 1.3 Short-Horizon Reversal & Market-Specific Mean Reversion
- **Primary Sources:**
  - Jegadeesh (1990), *"Evidence of Predictable Behavior of Security Returns"*, *Journal of Finance*, 45(3), 881–898.
  - Lehmann (1990), *"Fads, Martingales, and Market Efficiency"*, *Quarterly Journal of Economics*, 105(1), 1–28.
  - Avellaneda & Lee (2010), *"Statistical Arbitrage in the U.S. Equities Market"*, *Quantitative Finance*, 10(7), 761–782.
  - Shen, Urquhart & Wang (2020), *Economics Letters* (Intraday reversal and overnight momentum in Bitcoin).
- **Gross vs. Net & Tradability:**
  - Short-horizon return reversal (`TC_007`) and Bollinger/VWAP mean reversion (`TC_005`, `TC_006`) show high gross win rates ($55\%\text{--}64\%$) during `RANGE_BOUND` regimes (`ADX < 22`), but suffer from **severe negative skewness** (fat left tails when a range transitions into a liquidation cascade or macro breakout) and **high fee sensitivity** (`[FACT]`).
  - **Practical Tradability Rule:** Mean-reversion strategies on `BTCUSDT`/`ETHUSDT` (`15m`–`1h`) are **untradable without two mandatory guards**:
    1. A strict **Regime Veto** (`MarketRegimeEngine != TRENDING_UP/DOWN` and `!= DELEVERAGING_PANIC`).
    2. **Post-only / Maker limit execution** (or minimum expected excursion $\ge 4 \times$ round-trip realistic cost).

---

### 1.4 Breakout & Volatility-Expansion Strategies
- **Primary Sources:**
  - Brock, Lakonishok & LeBaron (1992), *"Simple Technical Trading Rules and the Stochastic Properties of Stock Returns"*, *Journal of Finance*, 47(5), 1731–1764.
  - Engle (1982), *"Autoregressive Conditional Heteroscedasticity"*, *Econometrica*, 50(4), 987–1007; Bollerslev (1986) *J. Econometrics* (GARCH volatility clustering).
  - Crabel (1990), *Day Trading with Short Term Price Patterns and Opening Range Breakout*.
- **Empirical Evidence vs. CBT Real-Data Replication:**
  - **Crucial Distinction:** Unconditioned price breakouts (`TC_009`, legacy `Breakout Buy` in `engine/rules.py`) that buy immediately near a recent 15m swing high **failed catastrophically on real Binance `BTCUSDT` 15m data** (`2025-01-01` to `2026-04-29`, `-0.630R gross / -0.904R net`, `PF = 0.225`, `[FACT]`). In modern crypto perpetual markets, obvious 15m swing highs are stop-hunted before reversing.
  - Conversely, **Volatility-Compression Breakouts (`TC_010`)** on `1h`/`4h` timeframes — conditioned on multi-bar Bollinger/ATR percentile compression (`< 20th percentile`) plus confirmed candle close and volume displacement (`RVOL > 1.5`) — exploit empirically verified GARCH volatility clustering (`[INFERENCE]`).

---

### 1.5 Carry, Perpetual Funding Rates & Futures Basis
- **Primary Sources:**
  - Koijen, Moskowitz, Pedersen & Vrugt (2018), *"Carry"*, *Journal of Financial Economics*, 127(2), 197–225.
  - Ackerer, Hugonnier & Jermann (2024), *"Perpetual Futures Pricing"*, *Mathematical Finance*, 34(2).
  - Schmeling, Schrimpf & Todorov (2023), *"Crypto Carry"*, *BIS Working Paper No. 1087* (Analyzing BTC/ETH spot-futures basis and perpetual funding carry, 2017–2023).
- **Empirical Findings (`[FACT]`):**
  - Crypto perpetual funding rates and quarterly basis exhibit some of the highest documented gross Sharpe ratios in digital assets ($SR_{\text{gross}} \approx 1.8\text{--}3.0$ for delta-neutral Spot-Long / Perp-Short carry during bull/neutral regimes) because retail demand for long leverage is structurally inelastic and balance-sheet arbitrage capital is segmented.
  - **Directional Conditioning (`TC_039`):** Even for a directional-only futures desk, funding rate Z-scores ($Z_{\text{funding}}$) and Open Interest changes ($\Delta \text{OI}$) act as high-value positioning filters: extreme positive funding ($Z > 2.2$) with stalling price predicts negative forward 24h–72h returns (long squeeze risk), whereas negative funding ($Z < -1.5$) with bullish structure break (`BOS`) predicts strong short-covering rallies.

---

### 1.6 Statistical Arbitrage & Cointegration (`BTC` vs. `ETH`)
- **Primary Sources:**
  - Engle & Granger (1987), *"Co-Integration and Error Correction"*, *Econometrica*, 55(2), 251–276.
  - Gatev, Goetzmann & Rouwenhorst (2006), *"Pairs Trading: Performance of a Relative-Value Arbitrage Rule"*, *Review of Financial Studies*, 19(3), 797–827.
  - Leung & Nguyen (2019), *"Constructing Cointegrated Cryptocurrency Portfolios for Statistical Arbitrage"*, *Studies in Economics and Finance*.
- **Empirical Findings & Limitations:**
  - While `BTCUSDT` and `ETHUSDT` have high return correlation ($\rho \approx 0.75\text{--}0.88$), **correlation is not cointegration** (`[FACT]`). The log-price spread $\ln P_{\text{ETH}} - \beta \ln P_{\text{BTC}}$ frequently undergoes non-stationary structural drifts (e.g., the 2022–2025 `ETH/BTC` secular downtrend from `0.085` to `< 0.035`).
  - Therefore, `TC_033` (Cointegration Pairs Trading) and `TC_034` (Spread Mean Reversion) **must** gate entries on rolling Augmented Dickey-Fuller (ADF) stationarity ($p < 0.05$), short Ornstein-Uhlenbeck half-lives ($\tau < 48$ hours), and a strict time-stop / max Z-score stop ($|Z| > 3.5$).

---

### 1.7 Order-Flow & Market Microstructure Effects
- **Primary Sources:**
  - Kyle (1985), *"Continuous Auctions and Insider Trading"*, *Econometrica*, 53(6), 1315–1335.
  - Easley, López de Prado & O'Hara (2012), *"Flow Toxicity and Liquidity in a High-Frequency World"*, *Review of Financial Studies*, 25(5), 1457–1493 (VPIN).
  - Cont, Kukanov & Stoikov (2014), *"The Price Impact of Order Book Events"*, *Journal of Financial Econometrics*, 12(1), 47–88 (Order Flow Imbalance / OBI).
  - Silantyev (2019), *"Order Flow Analysis of Cryptocurrency Markets"*, *Digital Finance*.
- **Correlation vs. Predictive Value & Horizon Decay:**
  - Contemporaneous Order Book Imbalance (`TC_031`) and Cumulative Volume Delta (`TC_030`) have an $R^2 > 0.60$ with **same-bar** price changes, which is an **observed contemporaneous correlation, NOT out-of-sample predictive alpha** (`[FACT]`).
  - Predictive forecasting power of L2 OBI decays exponentially with a half-life of **seconds to a few minutes**. On `15m`–`4h` bars, OBI and VPIN (`TC_029`–`TC_032`) should be used as **execution-timing filters (`EXECUTION_METHOD`) and liquidity-toxicity vetoes**, not standalone directional strategies paying taker fees.

---

### 1.8 Smart Money Concepts (SMC / ICT) & Discretionary Price-Action Hypotheses
- **Primary Sources:**
  - Osler (2003), *"Currency Orders and Exchange Rate Dynamics: An Explanation for the Predictive Success of Technical Analysis"*, *Journal of Finance*, 58(5), 1791–1820; Osler (2005), *"Stop-Loss Orders and Price Cascades in Currency Markets"*, *Journal of International Money and Finance* (Empirical verification that stop-loss and take-profit orders cluster at round numbers and recent swing highs/lows, creating self-reinforcing cascades when triggered).
  - Bouchaud, Bonart, Donier & Gould (2018), *Trades, Quotes and Prices: Financial Markets Under the Microscope*, Cambridge University Press (Microstructure mechanics of liquidity voids and impact relaxation).
- **Scientific Deconstruction of SMC/ICT Terminology (`[HYPOTHESIS]` $\to$ `[TESTABLE MECHANISM]`):**
  - Discretionary SMC/ICT concepts ("Liquidity Sweep", "Fair Value Gap", "Order Block", "Change of Character") have **zero peer-reviewed academic validation under retail ICT marketing names**, and retail claims of "80–90% win rates" are survivorship-biased chart cherry-picking (`[FACT]`).
  - However, when stripped of lore and formalized mathematically, three sub-mechanisms map to testable microstructure hypotheses:
    1. **Stop-Cascade Exhaustion (`TC_017` / `TC_022`):** Price piercing a clustered swing high/low triggers stop-market orders (Osler, 2005). If passive liquidity absorbs the cascade and price closes back inside the range *with a confirmed Market Structure Shift (`MSS`)* in a range-bound or HTF-aligned regime, a mean-reverting snapback can occur. **Without MSS and HTF regime filtering, fading sweeps loses money (`-0.448R` to `-0.584R net` in CBT P12.6 `[FACT]`).**
    2. **Trend Pullback to Displacement Imbalance (`TC_013` / `TC_015` / `TC_019`):** Retracements into the 50% discount zone or unmitigated 3-bar displacement gap (`FVG`) of an established trend are mathematically a volatility-conditioned **Trend Pullback** (`FAM_04`). In CBT's real-data run (`2026-08-14`), `Buy Pullback` (`+1.077R gross`) and `Sell Pullback` (`+0.974R net`) were the **only** setups showing positive 24h expectancy, though requiring larger non-overlapping sample sizes ($N_{\text{eff}}$).

---

### 1.9 Volatility & Regime-Conditioned Strategies
- **Primary Sources:**
  - Hamilton (1989), *"A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle"*, *Econometrica*, 57(2), 357–384.
  - Moreira & Muir (2017), *"Volatility-Managed Portfolios"*, *Journal of Finance*, 72(4), 1611–1644.
  - Ang & Bekaert (2002), *"International Asset Allocation With Regime Shifts"*, *Review of Financial Studies*, 15(4), 1137–1187.
- **Empirical Findings (`[FACT]`):**
  - Conditioning strategy activation on observable volatility and efficiency-ratio regimes (`TC_053`) and scaling exposure inversely with realized volatility (`TC_054`) reliably reduces left-tail kurtosis and maximum drawdown across both futures and crypto.

---

### 1.10 Portfolio Diversification, Risk Allocation & Multiple-Testing Defense
- **Primary Sources:**
  - López de Prado (2016), *"Building Diversified Portfolios that Outperform Out-of-Sample"*, *Journal of Portfolio Management*, 42(4), 59–69 (Hierarchical Risk Parity).
  - Bailey & López de Prado (2014), *"The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality"*, *Journal of Portfolio Management*, 40(5), 94–107.
  - White (2000), *"A Reality Check for Data Snooping"*, *Econometrica*, 68(5), 1097–1126.
- **Empirical Findings (`[FACT]`):**
  - Combining multiple variations of the same family (e.g., 5 trend indicators) provides an illusion of confluence while concentrating drawdown risk ($\rho_{\text{DD}} > 0.85$). True Sharpe improvement requires combining **orthogonal return drivers**: (1) Intermediate Trend / Pullback (`FAM_01` / `FAM_04`), (2) Range-Conditioned Reversion (`FAM_02`), and (3) Derivatives Positioning / Carry Conditioning (`FAM_10`), governed by strict correlation caps ($\rho \le 0.70$) and Deflated Sharpe Ratio ($\text{DSR} \ge 0.95$).

---

## 2. Provisional Research-Priority Ranking for BTC & ETH Futures

We do **not** claim a definitive global profitability ranking. Below is the evidence-backed **Provisional Research-Priority Ranking** for CBT/SKY empirical evaluation (Candidates A–F):

| Priority Rank | Candidate Group & Concept IDs | Target Horizon & Timeframe | Evidence Confidence | Rationale for Testing on BTC/ETH Futures | Primary Risk / Hurdle to Pass |
|:---:|:---|:---|:---:|:---|:---|
| **Priority 1** | **Candidate B: Trend Pullback & Continuation** (`TC_013`, `TC_014`, `TC_015`) | `1h` / `4h` bars (12h–48h holding) | **HIGH** | Strongest internal CBT real-data lead (`Buy Pullback +1.077R gross`, `Sell Pullback +0.974R net` on 24h horizon) combined with solid price-action/trend empirical backing; enters at better prices than raw breakouts. | Must prove statistical significance under **non-overlapping** $N_{\text{eff}} \ge 100$ and survive $1.5\times$ / $2.5\times$ cost stress. |
| **Priority 2** | **Candidate A: Time-Series Momentum & Vol-Adjusted Trend** (`TC_001`, `TC_002`, `TC_004`) | `4h` / `1d` bars (3d–14d holding) | **HIGH** | Strongest peer-reviewed academic replication in crypto (Liu & Tsyvinski, 2021; Liu et al., 2022); low turnover minimizes taker fee drag. | Whipsaw drawdown during multi-month sideways consolidation ranges; requires regime filter (`TC_053`). |
| **Priority 3** | **Candidate E: Funding-Rate & Positioning-Conditioned Trend/Carry** (`TC_037`, `TC_039`, `TC_042`) | `4h` / `8h` / `1d` | **HIGH** | Structural economic risk transfer premium documented in BIS & academic crypto derivatives studies (Schmeling et al., 2023; Ackerer et al., 2024); orthogonal to pure price technicals. | Requires complete historical 8h funding rate & Open Interest series joined to OHLCV without lookahead. |
| **Priority 4** | **Candidate C: Volatility-Compression Breakout** (`TC_010`, `TC_003`) | `1h` / `4h` bars | **MEDIUM-HIGH** | Exploits GARCH volatility clustering while avoiding the fatal flaw of unconditioned swing breakouts (`TC_009`, which failed at `-0.904R net`). | High false-expansion rate if volume displacement (`RVOL > 1.5`) is absent; vulnerable to stop-hunt wicks. |
| **Priority 5** | **Candidate D: Regime-Conditioned Mean Reversion** (`TC_005`, `TC_006`, `TC_008`) | `15m` / `1h` / `4h` ( strictly in `RANGE_BOUND`) | **MEDIUM** | Provides negative/low correlation to Trend Following (`FAM_01`), stabilizing portfolio equity during sideways markets (`ADX < 22`). | Left-tail blowout risk if the range breaks into a liquidation cascade; high sensitivity to maker vs. taker fees. |
| **Priority 6** | **Candidate F: Formalized SMC/ICT Setups (Sweep + MSS / FVG Retest)** (`TC_017`, `TC_019`, `TC_022`) | `1h` / `4h` bars | **LOW-MEDIUM (Quarantined / Hypothesis)** | Already partially built in `core/sky_intelligence/`; must be tested fairly against Candidates A–E to determine whether SMC rules add genuine incremental value over simpler pullback (`TC_014`) and range-reversion (`TC_005`) baselines. | Legacy 15m `Sweep Reversal` failed after costs (`-0.448R` / `-0.584R net`); high rule complexity and multi-parameter overfitting risk. |

