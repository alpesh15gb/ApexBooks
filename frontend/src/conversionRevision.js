import { supportsFeature } from './capabilities.js';
export function captureConversionSource(source, edit) {
  if (edit || !source?.id) return null;
  return { id: source.id, version: Object.hasOwn(source.data || {}, "version") ? source.data.version : 0 };
}
export function conversionBlockReason(source, capabilities, features = []) {
  if (!source) return '';
  if (!Number.isSafeInteger(source.version) || source.version < 0)
    return 'The source revision is invalid. Close this form and reopen the source to review its current details before converting.';
  if (capabilities === null) return 'Checking API support for protected document conversion. Wait or check again before saving.';
  if (capabilities?.status === 'unverified') return 'Protected conversion support could not be verified. Retry the API support check; your reviewed details stay in this form.';
  if (supportsFeature(capabilities?.features || features, 'document_conversion_revisions')) return '';
  return 'The connected API needs an update for protected document conversion. Update the API and check support again before saving. Normal new documents and edits remain available.';
}
const DEFINITE_SOURCE_CONFLICTS = new Set([
  'Conversion source revision required; update the app and reopen the source document before converting',
  'Conversion source changed; reopen it and review the conversion again',
]);
export function isDefiniteConversionConflict(error) {
  return error?.status === 409 && DEFINITE_SOURCE_CONFLICTS.has(error.message);
}
