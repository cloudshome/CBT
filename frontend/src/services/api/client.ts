/**
 * Base HTTP Client for CBT / SKY Quantitative Engine
 * Modular Transport Layer with API Key Authentication and Electron file:// support.
 */

export const getApiBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    if (window.location.protocol === 'file:') {
      return 'http://127.0.0.1:8000';
    }
  }
  return '';
};

export const BASE_URL = getApiBaseUrl();

let _apiKey: string =
  (typeof window !== 'undefined' ? localStorage.getItem('cbt_api_key') || '' : '') ||
  (((import.meta as unknown as { env?: Record<string, string> })?.env?.VITE_API_KEY) || '');

export function setApiKey(key: string): void {
  _apiKey = key;
  if (typeof window !== 'undefined') {
    if (key) {
      localStorage.setItem('cbt_api_key', key);
    } else {
      localStorage.removeItem('cbt_api_key');
    }
  }
}

export function getApiKey(): string {
  return _apiKey;
}

export function authHeaders(extraHeaders?: HeadersInit): HeadersInit {
  const headers = new Headers(extraHeaders || {});
  if (_apiKey && !headers.has('X-API-Key') && !headers.has('Authorization')) {
    headers.set('X-API-Key', _apiKey);
  }
  return headers;
}

export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = authHeaders(init?.headers);
  if (init?.body && typeof init.body === 'string' && !(headers as Headers).has('Content-Type')) {
    (headers as Headers).set('Content-Type', 'application/json');
  }
  let finalInput = input;
  if (
    typeof input === 'string' &&
    input.startsWith('/') &&
    typeof window !== 'undefined' &&
    window.location.protocol === 'file:'
  ) {
    finalInput = `http://127.0.0.1:8000${input}`;
  }
  return fetch(finalInput, {
    ...init,
    headers,
  });
}
