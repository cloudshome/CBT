# Connecting SKY to the real world

Everything below is also visible and testable in the dashboard:
**open http://localhost:8050 → 🔌 Connections**. Each card says what the link
gives you, whether it is live right now, and the exact steps to switch it on.
You never have to read this file — it exists so the steps are also written down.

---

## Step 1 — the real market (required, free, no account)

By default a fresh checkout may run in **demo mode**, which uses synthetic
candles so the app works offline. Synthetic prices are not the market.

```bash
# in your .env
DEMO_MODE=0
```

Restart with `python3 main.py`. The Connections tab should now show
**REAL MARKET** instead of **DEMO MODE**.

This gives you, with no account and no API key:

| Link | What it gives you |
|---|---|
| Binance market data | Live candles for BTC, ETH, gold proxy and any USDT pair |
| Futures: funding / OI / long-short | How crowded and leveraged the market is |
| Crypto news feeds | CoinTelegraph / CoinDesk / Decrypt headlines + sentiment |
| Fear & Greed index | The crowd's emotional temperature |
| Equities / macro | Risk-on vs risk-off from the S&P 500 |
| Market cap & BTC dominance | Whether money is rotating into or out of alts |

> Some regions geo-block Binance's **futures** endpoints. If that is you,
> funding and open interest simply go missing and the desk says so. It never
> guesses a number it could not fetch.

---

## Step 2 — alerts on your phone (optional, free)

So you are not chained to the screen waiting for a setup.

### Telegram

1. Open Telegram and message **@BotFather**, send `/newbot`, follow the prompts.
2. Copy the token it gives you into `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=123456:ABC-your-token
   ```
3. Send your new bot any message (this creates the chat).
4. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and
   copy the `"chat":{"id":...}` number into `.env`:
   ```bash
   TELEGRAM_CHAT_ID=987654321
   ```
5. Restart SKY → Connections tab → **Send me a test alert**.

### Discord

1. Discord → Server Settings → Integrations → Webhooks → New Webhook.
2. Copy the URL into `.env`:
   ```bash
   DISCORD_ANNOUNCE_WEBHOOK=https://discord.com/api/webhooks/...
   ```
3. Restart SKY → Connections tab → **Send me a test alert**.

---

## Step 3 — AI narrative (optional)

Plain-language explanation of a setup. **Entirely optional**: the desk already
explains itself with rules, and no decision ever depends on an LLM.

Groq has a free tier:

```bash
LLM_PROVIDER=groq
OPENAI_API_KEY=gsk_your_key
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=openai/gpt-oss-120b
```

OpenAI or Gemini work too — see `.env.example`.

---

## Step 4 — your exchange account, READ-ONLY (optional)

This shows your **real balance** and **real open orders** beside the paper
book, so the position-size calculator uses your true equity instead of a number
you typed in.

### Create the key correctly

1. Binance → **API Management** → Create API key.
2. Tick **ONLY “Enable Reading”.**
3. Leave **every** trading permission **OFF**. Leave withdrawals **OFF**.
4. Restrict the key to your **IP address**.
5. Put it in `.env`:
   ```bash
   BINANCE_READ_API_KEY=your_key
   BINANCE_READ_API_SECRET=your_secret
   ```
6. Restart SKY → Connections tab → **Test this connection**.

### Why this is safe

`data/exchange_account.py` is built so that trading is not merely discouraged,
it is **absent**:

- there is exactly one request primitive, and it issues **GET** only;
- it signs a request only if the path is in `READ_ONLY_PATHS` (account,
  open orders, recent trades) — anything else raises before a request is made;
- there is no `requests.post` anywhere in the file, enforced by a test;
- if you paste a key that *does* carry trade or withdraw permission, the
  dashboard flags it in red and tells you to replace it. SKY still will not use
  it for anything but reading.

---

## Step 5 — real trading keys

**Not supported, deliberately.**

SKY has no order-placement code. That is not an oversight — it is the current
correct state of the project, because SKY **has not yet proven an edge**. Every
setup is still unproven, which is exactly why the risk gate blocks nearly every
trade (see the 🔓 **Evidence** tab).

Connecting live execution to a system with no measured expectancy is the
fastest way to lose money. The honest order of operations is:

1. Prove at least one setup: 100 graded backtest trades, 20 decided paper
   trades, positive expectancy **net of costs** — the Evidence tab tracks this.
2. Confirm it is not curve-fitted: `Scorecard` with quality, and the
   `Look-ahead guard`.
3. Paper-trade it live for a meaningful stretch, journalling every trade.
4. Only then consider real money — and start at a size where being wrong is
   genuinely irrelevant to you.

When that day comes, execution should be a **new, separate module** with its
own human confirmation step, never an extension of the read-only client.

---

## Checking it all worked

Dashboard → 🔌 **Connections** shows one card per link with a live/not-live
badge and a **Test this connection** button. The strip at the top summarises:

- `REAL MARKET · 6/10 links live` → you are connected.
- `DEMO MODE` → you are still on synthetic data; set `DEMO_MODE=0`.
- `No live market data` → check your internet or region.

From a terminal, the same information:

```bash
python3 main.py doctor      # full readiness report
python3 main.py health      # data feeds, DB, risk gate, MCP
```
