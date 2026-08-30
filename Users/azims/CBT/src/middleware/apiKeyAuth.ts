import { Request, Response, NextFunction } from 'express';
import crypto from 'crypto';

/**
 * API Key Authentication Middleware
 *
 * Checks for a valid API key in either:
 *   - `Authorization: Bearer <key>` header
 *   - `X-API-Key: <key>` header
 *
 * Behavior:
 *   - If API_KEY env var is not set: middleware passes through (backward compatible / dev mode)
 *   - If API_KEY is set: requests must include a matching key or receive 401/403
 */

function extractApiKey(req: Request): string | null {
  // Check Authorization: Bearer <key>
  const authHeader = req.headers['authorization'];
  if (authHeader && authHeader.startsWith('Bearer ')) {
    return authHeader.slice(7).trim();
  }

  // Check X-API-Key header
  const xApiKey = req.headers['x-api-key'];
  if (typeof xApiKey === 'string' && xApiKey.trim()) {
    return xApiKey.trim();
  }

  return null;
}

/**
 * Constant-time string comparison to prevent timing attacks.
 */
function timingSafeEqual(a: string, b: string): boolean {
  try {
    return crypto.timingSafeEqual(
      Buffer.from(a, 'utf8'),
      Buffer.from(b, 'utf8')
    );
  } catch {
    let result = 0;
    for (let i = 0; i < a.length; i++) {
      result |= a.charCodeAt(i) ^ b.charCodeAt(i);
    }
    return result === 0;
  }
}

/**
 * Middleware that enforces API key authentication on sensitive routes.
 * Dynamically checks process.env.API_KEY on every request.
 */
export function apiKeyAuth(req: Request, res: Response, next: NextFunction): void {
  const configuredKey = process.env.API_KEY || '';

  // If no API_KEY is configured, pass through (backward compatible / dev mode)
  if (!configuredKey) {
    next();
    return;
  }

  const providedKey = extractApiKey(req);

  if (!providedKey) {
    res.status(401).json({
      error: 'Authentication required',
      message: 'Provide API key via Authorization: Bearer <key> or X-API-Key header',
    });
    return;
  }

  // Constant-time comparison to prevent timing attacks
  if (providedKey.length !== configuredKey.length || !timingSafeEqual(providedKey, configuredKey)) {
    res.status(403).json({
      error: 'Invalid API key',
    });
    return;
  }

  next();
}
