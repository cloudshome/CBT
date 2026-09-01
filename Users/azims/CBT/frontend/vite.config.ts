import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * SKY Vite Proxy Configuration
 * =============================================================================
 * Two backends run simultaneously:
 *
 *   Node/Express  → http://localhost:3000
 *     Handles: /api/candles, /api/mtf, /api/scan, /api/paper,
 *              /api/desk, /api/tickers, /api/institutional
 *
 *   FastAPI/Python → http://localhost:8000
 *     Handles: /api/sky, /api/decision, /api/prediction,
 *              /api/scenarios, /api/path-simulation, /api/shadow,
 *              /api/lab, /api/governance, /api/league, /api/command,
 *              /api/market, /api/dossier, /api/smc
 *              WS: /ws
 *
 * The proxy order matters — more-specific prefixes must appear BEFORE
 * the catch-all '/api' rule that falls back to Node.
 * =============================================================================
 */

// Python FastAPI endpoint prefixes (port 8000)
const PYTHON_PREFIXES = [
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
  '/api/chart',
  '/api/memory',
  '/api/ai',
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
  plugins: [react()],
  server: {
    port: 5173,
    proxy: proxyMap,
  },
});
