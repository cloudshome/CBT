import { GoogleGenAI } from '@google/genai';
import { DetectionResult, SetupSuggestion } from '../types';
import { IndicatorPoint } from '../utils/indicators';

export class GeminiServiceError extends Error {
  public statusCode: number;

  constructor(message: string, statusCode = 503) {
    super(message);
    this.name = 'GeminiServiceError';
    this.statusCode = statusCode;
  }
}

export interface MarketBriefInput {
  symbol: string;
  timeframe: string;
  lastPrice: number;
  highPrice: number;
  lowPrice: number;
  trend: string;
  ema?: IndicatorPoint[];
  rsi?: IndicatorPoint[];
  smc: DetectionResult;
  setups: SetupSuggestion[];
}

export interface MarketBriefOutput {
  symbol: string;
  timeframe: string;
  executiveSummary: string;
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  keyLevels: {
    support: number[];
    resistance: number[];
    invalidation?: number;
  };
  riskAssessment: string;
  metrics: {
    lastPrice: number;
    ema?: number;
    rsi?: number;
    trend: string;
  };
  timestamp: number;
}

let geminiClientInstance: GoogleGenAI | null = null;

/**
 * Lazy initializer for GoogleGenAI client
 */
export function getGeminiClient(): GoogleGenAI {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey || apiKey.trim() === '') {
    throw new GeminiServiceError(
      'GEMINI_API_KEY is not configured or is missing in the environment.',
      503
    );
  }

  if (!geminiClientInstance) {
    geminiClientInstance = new GoogleGenAI({ apiKey });
  }

  return geminiClientInstance;
}

/**
 * Resets cached client instance (useful in unit testing)
 */
export function resetGeminiClient(): void {
  geminiClientInstance = null;
}

const DEFAULT_MODEL = 'gemini-2.5-flash';

/**
 * Generates an executive market intelligence brief from technical data
 */
export async function generateMarketBrief(
  data: MarketBriefInput,
  model = DEFAULT_MODEL
): Promise<MarketBriefOutput> {
  const ai = getGeminiClient();

  const latestEMA = data.ema && data.ema.length > 0 ? data.ema[data.ema.length - 1].value : undefined;
  const latestRSI = data.rsi && data.rsi.length > 0 ? data.rsi[data.rsi.length - 1].value : undefined;

  const prompt = `You are a Senior Quantitative Crypto Strategist and Desk Intelligence Lead at a top prop firm.
Analyze the following multi-timeframe market telemetry and quantitative Smart Money Concepts (SMC) scan for ${data.symbol} (${data.timeframe}):

--- TELEMETRY DATA ---
- Asset: ${data.symbol}
- Timeframe: ${data.timeframe}
- Current Price: ${data.lastPrice}
- Session Range: Low ${data.lowPrice} - High ${data.highPrice}
- Technical Indicators: EMA(14)=${latestEMA ?? 'N/A'}, RSI(14)=${latestRSI ?? 'N/A'}
- SMC Order Flow / Trend: ${data.trend}
- Detected FVGs: Bullish=${data.smc.stats.bullishFVGs} (${data.smc.stats.unmitigatedFVGs} unmitigated), Bearish=${data.smc.stats.bearishFVGs}
- Detected Order Blocks: Bullish=${data.smc.stats.bullishOBs}, Bearish=${data.smc.stats.bearishOBs}
- Trade Setups: ${JSON.stringify(data.setups)}

--- INSTRUCTIONS ---
Provide an institutional-grade market brief formatted as strict valid JSON (no markdown fences, pure JSON):
{
  "executiveSummary": "2-3 concise sentences on market structure, liquidity drivers, and momentum",
  "bias": "BULLISH" | "BEARISH" | "NEUTRAL",
  "keyLevels": {
    "support": [number, number],
    "resistance": [number, number],
    "invalidation": number
  },
  "riskAssessment": "Key risk factors (e.g. overbought RSI, unmitigated gap below, liquidity sweeps)"
}`;

  let responseText = '';
  try {
    const response = await ai.models.generateContent({
      model,
      contents: prompt,
    });
    responseText = response.text || '';
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes('429') || msg.includes('RESOURCE_EXHAUSTED')) {
      throw new GeminiServiceError(`Gemini API rate limit exceeded: ${msg}`, 429);
    }
    throw new GeminiServiceError(`Failed to generate market brief from Gemini: ${msg}`, 503);
  }

  interface ParsedGeminiBrief {
    executiveSummary?: string;
    bias?: string;
    keyLevels?: {
      support?: number[];
      resistance?: number[];
      invalidation?: number;
    };
    riskAssessment?: string;
  }

  // Parse JSON response safely
  let parsed: ParsedGeminiBrief = {};
  try {
    const cleanJson = responseText
      .replace(/```json/gi, '')
      .replace(/```/g, '')
      .trim();
    parsed = JSON.parse(cleanJson) as ParsedGeminiBrief;
  } catch {
    // Fallback parsing if LLM returned non-JSON text
    parsed = {
      executiveSummary: responseText.slice(0, 300) || `Market is currently in ${data.trend} at ${data.lastPrice}.`,
      bias: data.trend.includes('Bullish') ? 'BULLISH' : data.trend.includes('Bearish') ? 'BEARISH' : 'NEUTRAL',
      keyLevels: {
        support: [data.lowPrice],
        resistance: [data.highPrice],
        invalidation: data.setups[0]?.stopLoss || data.lowPrice,
      },
      riskAssessment: 'Standard market volatility and liquidity risks apply.',
    };
  }

  return {
    symbol: data.symbol,
    timeframe: data.timeframe,
    executiveSummary: parsed.executiveSummary || `Market structure indicates ${data.trend}.`,
    bias:
      parsed.bias === 'BULLISH' || parsed.bias === 'BEARISH' || parsed.bias === 'NEUTRAL'
        ? parsed.bias
        : 'NEUTRAL',
    keyLevels: {
      support: Array.isArray(parsed.keyLevels?.support) ? parsed.keyLevels.support : [data.lowPrice],
      resistance: Array.isArray(parsed.keyLevels?.resistance) ? parsed.keyLevels.resistance : [data.highPrice],
      invalidation: typeof parsed.keyLevels?.invalidation === 'number' ? parsed.keyLevels.invalidation : data.setups[0]?.stopLoss,
    },
    riskAssessment: parsed.riskAssessment || 'Maintain disciplined position sizing within risk parameters.',
    metrics: {
      lastPrice: data.lastPrice,
      ema: latestEMA,
      rsi: latestRSI,
      trend: data.trend,
    },
    timestamp: Date.now(),
  };
}

/**
 * Answers ad-hoc quantitative market questions grounded in provided market telemetry
 */
export async function askDesk(
  query: string,
  context?: Record<string, unknown>,
  model = DEFAULT_MODEL
): Promise<string> {
  const ai = getGeminiClient();

  const contextStr = context ? JSON.stringify(context, null, 2) : 'No extra telemetry context provided.';
  const prompt = `You are the Crypto Brain Terminal Desk AI Assistant. Answer the user question grounded in the provided quantitative context.

--- TELEMETRY CONTEXT ---
${contextStr}

--- USER QUESTION ---
${query}

--- INSTRUCTIONS ---
Be direct, mathematically grounded, and concise. Avoid fluff.`;

  try {
    const response = await ai.models.generateContent({
      model,
      contents: prompt,
    });
    return (response.text || '').trim();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes('429') || msg.includes('RESOURCE_EXHAUSTED')) {
      throw new GeminiServiceError(`Gemini API rate limit exceeded: ${msg}`, 429);
    }
    throw new GeminiServiceError(`Desk query failed: ${msg}`, 503);
  }
}
