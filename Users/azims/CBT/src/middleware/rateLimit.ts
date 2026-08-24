import { Request, Response, NextFunction } from 'express';

export interface RateLimitOptions {
  windowMs?: number;
  max?: number;
  message?: string;
}

interface ClientRecord {
  count: number;
  resetTime: number;
}

/**
 * Creates an in-memory IP-based rate limiting middleware
 */
export function createRateLimiter(options: RateLimitOptions = {}) {
  const windowMs = options.windowMs || 60 * 1000; // 1 minute default
  const max = options.max !== undefined ? options.max : 60; // 60 requests default
  const message = options.message || 'Too many requests, please try again later.';

  const hits = new Map<string, ClientRecord>();

  const limiter = (req: Request, res: Response, next: NextFunction): void => {
    // Determine client IP (support x-forwarded-for or socket address)
    const forwarded = req.headers['x-forwarded-for'];
    const ip =
      (typeof forwarded === 'string' ? forwarded.split(',')[0].trim() : req.socket.remoteAddress) ||
      '127.0.0.1';

    const now = Date.now();
    let record = hits.get(ip);

    if (!record || now >= record.resetTime) {
      record = {
        count: 0,
        resetTime: now + windowMs,
      };
      hits.set(ip, record);
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

  return limiter;
}

// Default 60 requests / minute rate limiter
export const defaultRateLimiter = createRateLimiter({
  windowMs: 60 * 1000,
  max: 60,
  message: 'Too many requests, please try again later.',
});
