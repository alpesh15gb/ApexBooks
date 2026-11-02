

export interface IdSetCacheConfig {
  storageKey: string;
  timestampKey: string;
  authKey: string;
  defaultTtlMs: number;
}

export interface IdSetCache {
  extractNumericId(id: string): string;
  hasAuthFlag(): boolean;
  getSyncCachedValue(productId: string): boolean | undefined;
  isIdInCache(productId: string): boolean;
  setCachedIds(ids: string[]): void;
  addIdToCache(productId: string): void;
  removeIdFromCache(productId: string): void;
  getAllCachedIds(): string[];
  cachedCount(): number;
  isCachePopulated(): boolean;
  isCacheStale(ttlMs?: number): boolean;
  getLastUpdateTime(): number;
  clearCache(): void;
  ensureIdsLoaded(fetcher: () => Promise<string[]>, ttlMs?: number): Promise<void>;
}

export function createIdSetCache(config: IdSetCacheConfig): IdSetCache {
  const { storageKey, timestampKey, authKey, defaultTtlMs } = config;

  let cachedIds: Set<string> | null = null;
  let inflight: Promise<void> | null = null;

  function extractNumericId(id: string): string {
    const match = String(id).match(/\d+$/);
    return match ? match[0] : id;
  }

  function hasAuthFlag(): boolean {
    try {
      return localStorage.getItem(authKey) === "true";
    } catch {
      return false;
    }
  }

  function getSyncCachedValue(productId: string): boolean | undefined {
    if (cachedIds !== null) {
      return cachedIds.has(extractNumericId(productId));
    }
    if (!hasAuthFlag()) return undefined;
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed: string[] = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          cachedIds = new Set(parsed);
          return cachedIds.has(extractNumericId(productId));
        }
      }
    } catch { /* ignore */ }
    return undefined;
  }

  function getOrInitCache(): Set<string> {
    if (cachedIds !== null) return cachedIds;
    if (!hasAuthFlag()) {
      cachedIds = new Set();
      return cachedIds;
    }
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed: string[] = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          cachedIds = new Set(parsed);
          return cachedIds;
        }
      }
    } catch { /* ignore */ }
    cachedIds = new Set();
    return cachedIds;
  }

  function persistAuthenticated(): void {
    try {
      localStorage.setItem(storageKey, JSON.stringify([...getOrInitCache()]));
      localStorage.setItem(timestampKey, String(Date.now()));
      localStorage.setItem(authKey, "true");
    } catch { /* ignore */ }
  }

  function isIdInCache(productId: string): boolean {
    return getOrInitCache().has(extractNumericId(productId));
  }

  function setCachedIds(ids: string[]): void {
    cachedIds = new Set(ids);
    persistAuthenticated();
  }

  function addIdToCache(productId: string): void {
    getOrInitCache().add(extractNumericId(productId));
    persistAuthenticated();
  }

  function removeIdFromCache(productId: string): void {
    getOrInitCache().delete(extractNumericId(productId));
    persistAuthenticated();
  }

  function getAllCachedIds(): string[] {
    return [...getOrInitCache()];
  }

  function cachedCount(): number {
    return getOrInitCache().size;
  }

  function isCachePopulated(): boolean {
    if (cachedIds !== null) return true;
    if (!hasAuthFlag()) return false;
    try {
      return localStorage.getItem(storageKey) !== null;
    } catch {
      return false;
    }
  }

  function isCacheStale(ttlMs: number = defaultTtlMs): boolean {
    if (!hasAuthFlag()) return true;
    try {
      const ts = localStorage.getItem(timestampKey);
      if (!ts) return true;
      return Date.now() - Number(ts) > ttlMs;
    } catch {
      return true;
    }
  }

  function getLastUpdateTime(): number {
    try {
      return Number(localStorage.getItem(timestampKey)) || 0;
    } catch {
      return 0;
    }
  }

  function clearCache(): void {
    cachedIds = new Set();
    inflight = null;
    try {
      localStorage.removeItem(storageKey);
      localStorage.removeItem(timestampKey);
      localStorage.removeItem(authKey);
    } catch { /* ignore */ }
  }

  function ensureIdsLoaded(
    fetcher: () => Promise<string[]>,
    ttlMs: number = defaultTtlMs,
  ): Promise<void> {
    if (isCachePopulated() && !isCacheStale(ttlMs)) {
      getOrInitCache();
      return Promise.resolve();
    }
    if (inflight) return inflight;
    inflight = fetcher()
      .then((ids) => {
        setCachedIds(ids);
      })
      .catch(() => { /* ignore */ })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  }

  return {
    extractNumericId,
    hasAuthFlag,
    getSyncCachedValue,
    isIdInCache,
    setCachedIds,
    addIdToCache,
    removeIdFromCache,
    getAllCachedIds,
    cachedCount,
    isCachePopulated,
    isCacheStale,
    getLastUpdateTime,
    clearCache,
    ensureIdsLoaded,
  };
}
