import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * SKY Vite Proxy Configuration
 * =============================================================================
 * Two backends run simultaneously:
 *
 *   FastAPI/Python → http://localhost:8000  (AUTHORITATIVE terminal surface)
 *     Handles: /api/candles, /api/tickers, /api/mtf, /api/scan, /api/paper,
 *              /api/desk, /api/institutional, /api/research, /api/kronos,
 *              /api/sky, /api/decision, /api/prediction, /api/scenarios,
 *              /api/path-simulation, /api/shadow, /api/lab, /api/governance,
 *              /api/league, /api/command, /api/market, /api/dossier, /api/smc,
 *              /api/voice, /api/telegram, /api/ingest, /api/strategy,
 *              /api/macro, /api/audit, /api/chart, /api/memory, /api/ai,
 *              /api/microstructure, /api/execution, /api/auditor
 *              WS: /ws
 *
 *   Node/Express → http://localhost:3000  (readiness/metrics/legacy fallback)
 *     Handles: /api/readiness, /api/metrics/*, and the '/api' catch-all
 *
 * PARITY CONTRACT: this list MUST stay identical to the Python locations in
 * frontend/nginx.conf and the Caddyfile — dev and prod must route the same
 * prefixes to the same backend.
 * =============================================================================
 */

// Python FastAPI endpoint prefixes (port 8000)
const PYTHON_PREFIXES = [
  '/api/candles',
  '/api/tickers',
  '/api/mtf',
  '/api/scan',
  '/api/research',
  '/api/knowledge',
  '/api/desk',
  '/api/paper',
  '/api/institutional',
  '/api/terminal',
  '/api/sky',
  '/api/decision',
  '/api/prediction',
  '/api/scenarios',
  '/api/path-simulation',
  '/api/shadow',
  '/api/lab',
  '/api/governance',
  '/api/league',
  '/api/command',
  '/api/market',
  '/api/dossier',
  '/api/smc',
  '/api/voice',
  '/api/telegram',
  '/api/ingest',
  '/api/strategy',
  '/api/macro',
  '/api/audit',
  '/api/microstructure',
  '/api/execution',
  '/api/auditor',
  '/api/burn-in',
  '/api/telemetry',
  '/api/incident',
  '/api/vault',
  '/api/chart',
  '/api/memory',
  '/api/ai',
  '/api/kronos',
  '/api/collective',
  '/api/volatility',
  '/api/arbitrage',
  '/api/mbo',
  '/api/system',
  '/api/health',
  '/api/auth',
  '/api/cexdex',
  '/api/heatmap',
  '/api/portfolio',
  '/api/strategist',
  '/api/v1',
  '/api/web3',
  '/api/testnet',
  '/ws',
];

const pythonProxy = {
  target: 'http://localhost:8000',
  changeOrigin: true,
  // WebSocket upgrade for /ws/terminal
  ws: true,
};

const nodeProxy = {
  target: 'http://localhost:3000',
  changeOrigin: true,
};

// Build the proxy map: Python prefixes first, then Node catch-all
const proxyMap: Record<string, typeof pythonProxy | typeof nodeProxy> = {};
for (const prefix of PYTHON_PREFIXES) {
  proxyMap[prefix] = pythonProxy;
}
proxyMap['/api'] = nodeProxy; // catch-all for Node routes

export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: proxyMap,
  },
});
