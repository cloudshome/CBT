import { openDB, DBSchema, IDBPDatabase } from 'idb';

export interface DrawingObject {
  id: string;
  type: 'TREND_LINE' | 'HORIZONTAL_RAY' | 'VERTICAL_LINE' | 'RECTANGLE' | 'FIB_RETRACEMENT' | 'POSITION_TOOL' | 'LONG_POSITION' | 'SHORT_POSITION';
  symbol: string;
  timeframe: string;
  points: Array<{
    timestamp: number;
    price: number;
  }>;
  color?: string;
  lineWidth?: number;
  data?: Record<string, unknown>; // e.g. R:R metrics for Position Tool
  createdAt: number;
}

export interface WorkspaceConfig {
  symbol: string;
  timeframe: string;
  chartType: 'CANDLE' | 'AREA' | 'LINE';
  indicators: {
    ema: { enabled: boolean; period: number; color: string };
    rsi: { enabled: boolean; period: number };
    vwap: { enabled: boolean; showBands: boolean };
    fvg: { enabled: boolean };
    orderBlocks: { enabled: boolean };
  };
  watchlist: string[];
  layout: {
    sidebarWidth: number;
    bottomHeight: number;
  };
}

interface CBTWorkspaceDBSchema extends DBSchema {
  drawings: {
    key: string;
    value: DrawingObject;
    indexes: { 'by-symbol': string };
  };
  workspace: {
    key: string;
    value: WorkspaceConfig;
  };
}

const DB_NAME = 'cbt_terminal_workspace_v1';
const DB_VERSION = 1;

let dbPromise: Promise<IDBPDatabase<CBTWorkspaceDBSchema>> | null = null;

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB<CBTWorkspaceDBSchema>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('drawings')) {
          const drawingStore = db.createObjectStore('drawings', { keyPath: 'id' });
          drawingStore.createIndex('by-symbol', 'symbol');
        }
        if (!db.objectStoreNames.contains('workspace')) {
          db.createObjectStore('workspace');
        }
      },
    });
  }
  return dbPromise;
}

export const WorkspacePersistence = {
  /**
   * Loads all drawings for a specific symbol.
   */
  async loadDrawings(symbol: string): Promise<DrawingObject[]> {
    try {
      const db = await getDB();
      const drawings = await db.getAllFromIndex('drawings', 'by-symbol', symbol);
      return drawings || [];
    } catch (err) {
      console.warn('Failed to load drawings from IndexedDB:', err);
      return [];
    }
  },

  /**
   * Saves or updates a drawing.
   */
  async saveDrawing(drawing: DrawingObject): Promise<void> {
    try {
      const db = await getDB();
      await db.put('drawings', drawing);
    } catch (err) {
      console.warn('Failed to save drawing to IndexedDB:', err);
    }
  },

  /**
   * Deletes a drawing by ID.
   */
  async deleteDrawing(id: string): Promise<void> {
    try {
      const db = await getDB();
      await db.delete('drawings', id);
    } catch (err) {
      console.warn('Failed to delete drawing from IndexedDB:', err);
    }
  },

  /**
   * Loads workspace configuration with LocalStorage fallback.
   */
  async loadWorkspaceConfig(): Promise<WorkspaceConfig | null> {
    try {
      const db = await getDB();
      const config = await db.get('workspace', 'default');
      if (config) return config;
    } catch (err) {
      console.warn('IndexedDB unavailable, checking localStorage:', err);
    }

    try {
      const local = localStorage.getItem('cbt_workspace_config');
      return local ? JSON.parse(local) : null;
    } catch {
      return null;
    }
  },

  /**
   * Saves workspace configuration.
   */
  async saveWorkspaceConfig(config: WorkspaceConfig): Promise<void> {
    try {
      const db = await getDB();
      await db.put('workspace', config, 'default');
    } catch (err) {
      console.warn('IndexedDB write failed, falling back to localStorage:', err);
    }

    try {
      localStorage.setItem('cbt_workspace_config', JSON.stringify(config));
    } catch (err) {
      console.warn('LocalStorage write failed:', err);
    }
  },
};
