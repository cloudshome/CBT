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
  source?: 'GEMINI_AI' | 'DETERMINISTIC_FALLBACK';
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

/**
 * Generates a deterministic quantitative intelligence brief based on SMC and indicator state.
 * Available for offline simulation, testing, or standalone mathematical analysis.
 */
export function generateDeterministicBrief(data: MarketBriefInput): MarketBriefOutput {
  const latestEMA = data.ema && data.ema.length > 0 ? data.ema[data.ema.length - 1].value : undefined;
  const latestRSI = data.rsi && data.rsi.length > 0 ? data.rsi[data.rsi.length - 1].value : undefined;

  const isBullish = data.trend.toLowerCase().includes('bullish') || (latestRSI !== undefined && latestRSI > 52 && (latestEMA === undefined || data.lastPrice > latestEMA));
  const isBearish = data.trend.toLowerCase().includes('bearish') || (latestRSI !== undefined && latestRSI < 48 && (latestEMA === undefined || data.lastPrice < latestEMA));
  const bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL' = isBullish ? 'BULLISH' : isBearish ? 'BEARISH' : 'NEUTRAL';

  const fvgStats = data.smc.stats;
  const summary = `${data.symbol} is currently printing ${data.trend} market structure on the ${data.timeframe} timeframe. ` +
    `Identified ${fvgStats.unmitigatedFVGs} unmitigated fair value gaps and ${fvgStats.bullishOBs + fvgStats.bearishOBs} structural order blocks. ` +
    (data.setups.length > 0 ? `Active setup: ${data.setups[0].type} at ${data.setups[0].entry} (R:R ${data.setups[0].riskRewardRatio}).` : 'Awaiting confirmation sweep.');

  return {
    symbol: data.symbol,
    timeframe: data.timeframe,
    executiveSummary: summary,
    bias,
    keyLevels: {
      support: [data.lowPrice, data.lowPrice * 0.99],
      resistance: [data.highPrice, data.highPrice * 1.01],
      invalidation: data.setups[0]?.stopLoss || data.lowPrice,
    },
    riskAssessment: `Quantitative risk score balanced. Monitor 15m RSI (${latestRSI ? latestRSI.toFixed(1) : 'N/A'}) for momentum exhaustion.`,
    metrics: {
      lastPrice: data.lastPrice,
      ema: latestEMA,
      rsi: latestRSI,
      trend: data.trend,
    },
    timestamp: Date.now(),
    source: 'DETERMINISTIC_FALLBACK',
  };
}

const DEFAULT_MODEL = 'gemini-2.5-flash';

/**
 * Generates an executive market intelligence brief from technical data using Gemini
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
    source: 'GEMINI_AI',
  };
}

/**
 * Ask Desk interactive Q&A endpoint
 */
export async function askDesk(
  question: string,
  marketContext: { symbol?: string; rsi?: number; trend?: string } = {},
  model = DEFAULT_MODEL
): Promise<string> {
  const ai = getGeminiClient();

  const prompt = `You are a Senior Crypto Trading Desk Lead.
A junior trader asks: "${question}"

Current Market Context:
- Asset: ${marketContext.symbol ?? 'N/A'}
- RSI(14): ${marketContext.rsi ?? 'N/A'}
- Trend: ${marketContext.trend ?? 'N/A'}

Provide a concise, direct, institutional trading answer (under 150 words).`;

  try {
    const response = await ai.models.generateContent({
      model,
      contents: prompt,
    });
    return response.text || 'Unable to generate response.';
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes('429') || msg.includes('RESOURCE_EXHAUSTED')) {
      throw new GeminiServiceError(`Gemini API rate limit exceeded: ${msg}`, 429);
    }
    throw new GeminiServiceError(`Desk query failed: ${msg}`, 503);
  }
}
