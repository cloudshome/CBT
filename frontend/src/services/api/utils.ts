/**
 * frontend/src/services/api/utils.ts
 * ==================================
 * Shared serialization, error handling, and candle normalization helpers.
 */

import { OHLCVCandle } from '../../types';

export class ApiError extends Error {
  public statusCode: number;
  public details?: unknown;

  constructor(message: string, statusCode: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.details = details;
  }
}

export async function handleResponse<T>(res: Response): Promise<T> {
  const isJson = res.headers.get('content-type')?.includes('application/json');
  const data = isJson ? await res.json() : null;

  if (!res.ok) {
    let errorMsg = res.statusText || 'API request failed';
    if (data) {
      if (typeof data.detail === 'string') {
        errorMsg = data.detail;
      } else if (Array.isArray(data.detail) && data.detail.length > 0) {
        errorMsg = data.detail
          .map((d: any) => (typeof d === 'string' ? d : d.msg || JSON.stringify(d)))
          .join(', ');
      } else if (typeof data.error === 'string') {
        errorMsg = data.error;
      } else if (typeof data.message === 'string') {
        errorMsg = data.message;
      }
    }
    throw new ApiError(errorMsg, res.status, data);
  }

  return data as T;
}

export function normalizeCandle(c: unknown): OHLCVCandle {
  if (Array.isArray(c)) {
    return [
      Number(c[0]) || 0,
      Number(c[1]) || 0,
      Number(c[2]) || 0,
      Number(c[3]) || 0,
      Number(c[4]) || 0,
      Number(c[5]) || 0,
    ];
  }
  const obj = c as Record<string, unknown> | null | undefined;
  return [
    Number(obj?.timestamp ?? obj?.time ?? 0),
    Number(obj?.open ?? 0),
    Number(obj?.high ?? 0),
    Number(obj?.low ?? 0),
    Number(obj?.close ?? 0),
    Number(obj?.volume ?? 0),
  ];
}
