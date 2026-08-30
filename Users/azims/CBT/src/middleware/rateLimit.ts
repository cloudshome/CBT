import { Request, Response, NextFunction } from 'express';
import crypto from 'crypto';

export interface RateLimitOptions {
  windowMs?: number;
  max?: number;
  authMax?: number;
  message?: string;
}

interface ClientRecord {
  count: number;
  resetTime: number;
}

/**
 * Creates an enhanced sliding-window rate limiting middleware with:
 * - Dual-tier limits: Higher quotas for authenticated requests (default: 180 req/min) vs public IPs (default: 60 req/min).
 * - Key hashing: Hashes API keys with SHA-256 for secure in-memory indexing.
 * - Automatic pruning: Unreferenced background cleanup preventing unbounded Map memory leaks.
 * - Standard headers: RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset, and Retry-After.
 */
export function createRateLimiter(options: RateLimitOptions = {}) {
  const windowMs = options.windowMs || Number(process.env.RATE_LIMIT_WINDOW_MS) || 60 * 1000;
  const publicMax = options.max !== undefined ? options.max : (Number(process.env.RATE_LIMIT_MAX) || 60);
  const authMax = options.authMax !== undefined ? options.authMax : (Number(process.env.RATE_LIMIT_AUTH_MAX) || 180);
  const message = options.message || 'Too many requests, please try again later.';

  const hits = new Map<string, ClientRecord>();

  // Periodically clean expired keys to prevent memory leak
  const cleanupTimer = setInterval(() => {
    const now = Date.now();
    for (const [key, record] of hits.entries()) {
      if (now >= record.resetTime) {
        hits.delete(key);
      }
    }
  }, 60 * 1000);

  // Allow Node process to exit without waiting on this background interval
  if (cleanupTimer && typeof cleanupTimer.unref === 'function') {
    cleanupTimer.unref();
  }

  const resolveClientKey = (req: Request): { key: string; isAuth: boolean } => {
    // 1. Check for API key in headers
    const authHeader = req.headers['authorization'];
    const xApiKey = req.headers['x-api-key'];
    let apiKey = '';
    if (authHeader && authHeader.startsWith('Bearer ')) {
      apiKey = authHeader.slice(7).trim();
    } else if (typeof xApiKey === 'string' && xApiKey.trim()) {
      apiKey = xApiKey.trim();
    }

    if (apiKey) {
      // Hash API key so raw credentials aren't indexed as plain text in memory
      const keyHash = crypto.createHash('sha256').update(apiKey).digest('hex').slice(0, 16);
      return { key: `auth:${keyHash}`, isAuth: true };
    }

    // 2. Fall back to IP address
    const forwarded = req.headers['x-forwarded-for'];
    const ip =
      (typeof forwarded === 'string' ? forwarded.split(',')[0].trim() : req.socket.remoteAddress) ||
      '127.0.0.1';
    return { key: `ip:${ip}`, isAuth: false };
  };

  const limiter = (req: Request, res: Response, next: NextFunction): void => {
    const { key, isAuth } = resolveClientKey(req);
    const max = isAuth ? authMax : publicMax;
    const now = Date.now();
    let record = hits.get(key);

    if (!record || now >= record.resetTime) {
      record = {
        count: 0,
        resetTime: now + windowMs,
      };
      hits.set(key, record);
    }

    record.count += 1;

    const remaining = Math.max(0, max - record.count);
    const resetSeconds = Math.ceil((record.resetTime - now) / 1000);

    res.setHeader('RateLimit-Limit', max);
    res.setHeader('RateLimit-Remaining', remaining);
    res.setHeader('RateLimit-Reset', resetSeconds);

    if (record.count > max) {
      res.setHeader('Retry-After', resetSeconds);
      res.status(429).json({ error: message });
      return;
    }

    next();
  };

  limiter.reset = () => {
    hits.clear();
  };

  limiter.cleanup = () => {
    clearInterval(cleanupTimer);
    hits.clear();
  };

  return limiter;
}

// Default 60 req/min for public IP, 180 req/min for authenticated keys
export const defaultRateLimiter = createRateLimiter({
  windowMs: 60 * 1000,
  max: 60,
  authMax: 180,
  message: 'Too many requests, please try again later.',
});
