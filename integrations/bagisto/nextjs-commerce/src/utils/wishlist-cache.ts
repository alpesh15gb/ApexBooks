import { WISHLIST_AUTH_KEY, WISHLIST_DEFAULT_TTL_MS, WISHLIST_STORAGE_KEY, WISHLIST_TIMESTAMP_KEY } from "./constants";
import { createIdSetCache } from "./id-set-cache";

const cache = createIdSetCache({
  storageKey: WISHLIST_STORAGE_KEY,
  timestampKey: WISHLIST_TIMESTAMP_KEY,
  authKey: WISHLIST_AUTH_KEY,
  defaultTtlMs: WISHLIST_DEFAULT_TTL_MS,
});

export const extractNumericId = cache.extractNumericId;
export const hasAuthFlag = cache.hasAuthFlag;
export const getSyncCachedValue = cache.getSyncCachedValue;
export const isIdInCache = cache.isIdInCache;
export const setCachedIds = cache.setCachedIds;
export const addIdToCache = cache.addIdToCache;
export const removeIdFromCache = cache.removeIdFromCache;
export const getAllCachedIds = cache.getAllCachedIds;
export const cachedCount = cache.cachedCount;
export const isCachePopulated = cache.isCachePopulated;
export const isCacheStale = cache.isCacheStale;
export const getLastUpdateTime = cache.getLastUpdateTime;
export const clearCache = cache.clearCache;
export const ensureIdsLoaded = cache.ensureIdsLoaded;