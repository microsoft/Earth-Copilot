/**
 * Rendering Logger
 * 
 * Centralized logging utilities for tile rendering operations.
 * Provides structured, categorized logging with easy enable/disable controls.
 * Helps with debugging tile rendering, performance tracking, and troubleshooting.
 * 
 * @module renderingLogger
 */

export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  NONE = 4
}

export enum LogCategory {
  TILE_FETCH = 'TILE-FETCH',
  TILE_LAYER = 'TILE-LAYER',
  MULTI_TILE = 'MULTI-TILE',
  SINGLE_TILE = 'SINGLE-TILE',
  CONFIG = 'CONFIG',
  BOUNDS = 'BOUNDS',
  ERROR = 'ERROR',
  PERFORMANCE = 'PERFORMANCE',
  MPC = 'MPC-APPROACH',
  TEST = 'TEST'
}

interface LoggerConfig {
  enabled: boolean;
  minLevel: LogLevel;
  enabledCategories: Set<LogCategory>;
  timestampEnabled: boolean;
  performanceTracking: boolean;
}

// Global logger configuration
const config: LoggerConfig = {
  enabled: true,
  minLevel: LogLevel.DEBUG,
  enabledCategories: new Set(Object.values(LogCategory)),
  timestampEnabled: false,
  performanceTracking: true
};

// Performance tracking storage
const performanceMarks: Map<string, number> = new Map();

/**
 * Configure the rendering logger
 * 
 * @param options - Configuration options
 */
export function configureLogger(options: Partial<LoggerConfig>): void {
  Object.assign(config, options);
}

/**
 * Enable/disable specific log categories
 * 
 * @param categories - Categories to enable
 * @param enable - true to enable, false to disable
 */
export function setCategories(categories: LogCategory[], enable: boolean = true): void {
  if (enable) {
    categories.forEach(cat => config.enabledCategories.add(cat));
  } else {
    categories.forEach(cat => config.enabledCategories.delete(cat));
  }
}

/**
 * Logs a debug message
 */
function log(
  level: LogLevel,
  category: LogCategory,
  message: string,
  data?: any
): void {
  if (!config.enabled || level < config.minLevel) {
    return;
  }

  if (!config.enabledCategories.has(category)) {
    return;
  }

  const prefix = ` [${category}]`;
  const timestamp = config.timestampEnabled ? `[${new Date().toISOString()}]` : '';
  
  const fullMessage = `${prefix}${timestamp} ${message}`;

  switch (level) {
    case LogLevel.DEBUG:
    case LogLevel.INFO:
      if (data !== undefined) {
        console.log(fullMessage, data);
      } else {
        console.log(fullMessage);
      }
      break;
    case LogLevel.WARN:
      if (data !== undefined) {
        console.warn(fullMessage, data);
      } else {
        console.warn(fullMessage);
      }
      break;
    case LogLevel.ERROR:
      if (data !== undefined) {
        console.error(fullMessage, data);
      } else {
        console.error(fullMessage);
      }
      break;
  }
}

/**
 * Log tile rendering start
 */
export function logRenderingStart(
  collection: string,
  isMultiTile: boolean,
  tileCount?: number
): void {
  const category = isMultiTile ? LogCategory.MULTI_TILE : LogCategory.SINGLE_TILE;
  const tileInfo = isMultiTile && tileCount ? ` (${tileCount} tiles)` : '';
  
  log(
    LogLevel.INFO,
    category,
    ` Starting ${isMultiTile ? 'multi-tile' : 'single-tile'} rendering for collection: ${collection}${tileInfo}`
  );
}

/**
 * Log tile rendering completion
 */
export function logRenderingComplete(
  collection: string,
  isMultiTile: boolean,
  successCount: number,
  errorCount: number = 0
): void {
  const category = isMultiTile ? LogCategory.MULTI_TILE : LogCategory.SINGLE_TILE;
  const emoji = errorCount === 0 ? '' : '';
  
  log(
    errorCount > 0 ? LogLevel.WARN : LogLevel.INFO,
    category,
    `${emoji} Rendering complete for ${collection}. Success: ${successCount}, Errors: ${errorCount}`
  );
}

/**
 * Log TileJSON fetch operation
 */
export function logTileJsonFetch(
  url: string,
  success: boolean,
  tileTemplate?: string,
  error?: string
): void {
  if (success && tileTemplate) {
    log(
      LogLevel.INFO,
      LogCategory.TILE_FETCH,
      ` TileJSON fetched successfully`,
      { url: url.substring(0, 100), template: tileTemplate.substring(0, 100) }
    );
  } else {
    log(
      LogLevel.ERROR,
      LogCategory.TILE_FETCH,
      ` TileJSON fetch failed: ${error}`,
      { url: url.substring(0, 100) }
    );
  }
}

/**
 * Log tile layer creation
 */
export function logTileLayerCreated(
  itemId: string,
  collection: string,
  config: {
    minZoom: number;
    maxZoom: number;
    opacity: number;
    bounds?: number[];
  }
): void {
  log(
    LogLevel.INFO,
    LogCategory.TILE_LAYER,
    ` Tile layer created for ${itemId}`,
    {
      collection,
      zoomRange: `${config.minZoom}-${config.maxZoom}`,
      opacity: config.opacity,
      hasBounds: !!config.bounds
    }
  );
}

/**
 * Log rendering configuration being used
 */
export function logRenderingConfig(
  collection: string,
  config: {
    minZoom: number;
    maxZoom: number;
    opacity: number;
    tileSize: number;
  }
): void {
  log(
    LogLevel.DEBUG,
    LogCategory.CONFIG,
    `Using rendering config for ${collection}`,
    config
  );
}

/**
 * Log bounds validation/clamping
 */
export function logBoundsProcessing(
  original: number[],
  clamped?: number[],
  valid: boolean = true
): void {
  if (!valid) {
    log(
      LogLevel.WARN,
      LogCategory.BOUNDS,
      ` Invalid bounds detected`,
      { original }
    );
  } else if (clamped && JSON.stringify(original) !== JSON.stringify(clamped)) {
    log(
      LogLevel.INFO,
      LogCategory.BOUNDS,
      `Bounds clamped for safety`,
      { original, clamped }
    );
  } else {
    log(
      LogLevel.DEBUG,
      LogCategory.BOUNDS,
      `Bounds validated`,
      { bounds: original }
    );
  }
}

/**
 * Log error with context
 */
export function logError(
  operation: string,
  error: any,
  context?: Record<string, any>
): void {
  log(
    LogLevel.ERROR,
    LogCategory.ERROR,
    ` Error during ${operation}: ${error?.message || String(error)}`,
    context
  );
}

/**
 * Log warning with context
 */
export function logWarning(
  message: string,
  context?: Record<string, any>
): void {
  log(
    LogLevel.WARN,
    LogCategory.ERROR,
    ` ${message}`,
    context
  );
}

/**
 * Start performance tracking for an operation
 */
export function startPerformanceTracking(operationId: string): void {
  if (!config.performanceTracking) {
    return;
  }
  
  performanceMarks.set(operationId, performance.now());
  log(
    LogLevel.DEBUG,
    LogCategory.PERFORMANCE,
    `Started tracking: ${operationId}`
  );
}

/**
 * End performance tracking and log duration
 */
export function endPerformanceTracking(operationId: string): number {
  if (!config.performanceTracking) {
    return 0;
  }

  const startTime = performanceMarks.get(operationId);
  
  if (!startTime) {
    log(
      LogLevel.WARN,
      LogCategory.PERFORMANCE,
      ` No start time found for: ${operationId}`
    );
    return 0;
  }

  const duration = performance.now() - startTime;
  performanceMarks.delete(operationId);

  log(
    LogLevel.INFO,
    LogCategory.PERFORMANCE,
    `${operationId} completed in ${duration.toFixed(2)}ms`
  );

  return duration;
}

/**
 * Log MPC approach specific information
 */
export function logMPCApproach(message: string, data?: any): void {
  log(LogLevel.INFO, LogCategory.MPC, message, data);
}

/**
 * Log multi-tile specific information
 */
export function logMultiTile(message: string, data?: any): void {
  log(LogLevel.INFO, LogCategory.MULTI_TILE, message, data);
}

/**
 * Log tile test information
 */
export function logTileTest(
  zoomXY: string,
  status: number,
  success: boolean,
  error?: any
): void {
  const emoji = success ? '' : '';
  log(
    success ? LogLevel.INFO : LogLevel.ERROR,
    LogCategory.TEST,
    `${emoji} Tile test ${zoomXY}: HTTP ${status}`,
    error ? { error } : undefined
  );
}

/**
 * Log DEM specific detection
 */
export function logDEMDetection(tileCount: number, urls?: string[]): void {
  log(
    LogLevel.INFO,
    LogCategory.MULTI_TILE,
    ` DEM (Digital Elevation Model) detected with ${tileCount} tiles for seamless coverage`,
    urls ? { sampleUrls: urls.slice(0, 3).map(u => u.substring(0, 80)) } : undefined
  );
}

/**
 * Log asset fix application
 */
export function logAssetFix(collection: string, fixType: string): void {
  log(
    LogLevel.INFO,
    LogCategory.CONFIG,
    ` Applied asset fix for ${collection}: ${fixType}`
  );
}

/**
 * Log symbol layer suppression (for DEM)
 */
export function logSymbolLayerSuppression(count: number): void {
  log(
    LogLevel.INFO,
    LogCategory.CONFIG,
    ` Suppressed ${count} symbol/label layers for better visualization`
  );
}

/**
 * Create a logger instance bound to a specific category
 */
export function createCategoryLogger(category: LogCategory) {
  return {
    debug: (message: string, data?: any) => log(LogLevel.DEBUG, category, message, data),
    info: (message: string, data?: any) => log(LogLevel.INFO, category, message, data),
    warn: (message: string, data?: any) => log(LogLevel.WARN, category, message, data),
    error: (message: string, data?: any) => log(LogLevel.ERROR, category, message, data),
  };
}

/**
 * Batch log multiple tile operations
 */
export function logTileBatch(
  operations: Array<{ itemId: string; success: boolean; error?: string }>
): void {
  const successCount = operations.filter(op => op.success).length;
  const errorCount = operations.length - successCount;

  log(
    LogLevel.INFO,
    LogCategory.MULTI_TILE,
    `Batch processing complete: ${successCount} succeeded, ${errorCount} failed`
  );

  // Log individual errors
  operations
    .filter(op => !op.success)
    .forEach(op => {
      log(
        LogLevel.ERROR,
        LogCategory.ERROR,
        `Failed to process ${op.itemId}: ${op.error}`
      );
    });
}

// Export commonly used presets
export const LogPresets = {
  /** Minimal logging - errors only */
  MINIMAL: (): void => {
    config.minLevel = LogLevel.ERROR;
  },
  
  /** Standard logging - info and above */
  STANDARD: (): void => {
    config.minLevel = LogLevel.INFO;
  },
  
  /** Verbose logging - everything including debug */
  VERBOSE: (): void => {
    config.minLevel = LogLevel.DEBUG;
  },
  
  /** Disable all logging */
  SILENT: (): void => {
    config.enabled = false;
  },
  
  /** Enable performance tracking only */
  PERFORMANCE_ONLY: (): void => {
    config.minLevel = LogLevel.INFO;
    setCategories([LogCategory.PERFORMANCE], true);
    setCategories(
      Object.values(LogCategory).filter(c => c !== LogCategory.PERFORMANCE),
      false
    );
  }
};
