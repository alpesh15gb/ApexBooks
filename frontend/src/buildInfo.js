export const WEB_VERSION = '1.5.0';
export function normalizedBuildRevision(value) {
  return typeof value === 'string' && /^(?:[a-f0-9]{40}|[a-f0-9]{64})$/i.test(value.trim()) ? value.trim().toLowerCase() : 'unknown';
}
export const WEB_BUILD_REVISION = normalizedBuildRevision(import.meta.env?.VITE_BUILD_SHA);
