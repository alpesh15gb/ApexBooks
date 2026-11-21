/** Bounded, checksum-verified transport. No archive parsing or financial writes. */
export const BACKUP_CHUNK_BYTES = 512 * 1024;
// Whole-buffer WebCrypto/Blob copies can exceed 5x archive size in a mobile browser.
// Larger complete archives require the file-backed native transfer, never omission.
export const MAX_WEB_ARCHIVE_BYTES = 16 * 1024 * 1024;
const HASH = /^[a-f0-9]{64}$/;
const stopIfAborted = signal => { if (signal?.aborted) throw new DOMException('Transfer cancelled', 'AbortError'); };
export async function sha256Bytes(value) {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
}
export function validateBackupManifest(manifest, maximumBytes = MAX_WEB_ARCHIVE_BYTES) {
  const size = manifest?.byte_count, count = manifest?.chunk_count, chunk = manifest?.chunk_size;
  const maximum = Math.min(maximumBytes, MAX_WEB_ARCHIVE_BYTES);
  if (!Number.isSafeInteger(size) || size < 1 || size > maximum)
    throw new Error('Archive size exceeds this browser transfer limit. Use a native client for a larger complete archive; no files will be omitted.');
  if (chunk !== BACKUP_CHUNK_BYTES || !Number.isSafeInteger(count) || count !== Math.ceil(size / chunk))
    throw new Error('Invalid backup chunk manifest');
  if (typeof manifest.sha256 !== 'string' || !HASH.test(manifest.sha256)) throw new Error('Invalid archive checksum');
  return { size, count, chunk, sha256: manifest.sha256 };
}

export async function downloadBackupChunks(manifest, getChunk, { signal, onProgress = () => {}, maximumBytes } = {}) {
  const plan = validateBackupManifest(manifest, maximumBytes), parts = [];
  let completed = 0;
  for (let index = 0; index < plan.count; index++) {
    stopIfAborted(signal);
    const response = await getChunk(index, { signal });
    stopIfAborted(signal);
    const part = response.bytes instanceof Uint8Array ? response.bytes : new Uint8Array(response.bytes);
    const expected = Math.min(plan.chunk, plan.size - completed);
    if (part.byteLength !== expected) throw new Error('Backup chunk length mismatch; no incomplete archive was saved');
    if (!HASH.test(response.sha256 || '') || await sha256Bytes(part) !== response.sha256)
      throw new Error('Backup chunk checksum mismatch; retry from the same export');
    const recorded = manifest.chunks?.find(row => row.index === index);
    if (recorded && (recorded.sha256 !== response.sha256 || recorded.byte_count !== part.byteLength))
      throw new Error('Backup snapshot changed during transfer');
    // Retain immutable Blob parts, not every source/network Uint8Array.
    parts.push(new Blob([part])); completed += part.byteLength;
    onProgress({ phase: 'download', completedBytes: completed, totalBytes: plan.size });
  }
  stopIfAborted(signal);
  const archive = new Blob(parts, { type: 'application/zip' });
  parts.length = 0;
  onProgress({ phase: 'verify', completedBytes: completed, totalBytes: plan.size });
  // WebCrypto accepts a bounded buffer. Native clients use incremental hashing;
  // this browser path deliberately refuses archives above the stated limit.
  if (await sha256Bytes(await archive.arrayBuffer()) !== plan.sha256) throw new Error('Complete archive checksum mismatch; nothing was saved');
  stopIfAborted(signal);
  onProgress({ phase: 'complete', completedBytes: completed, totalBytes: plan.size });
  return archive;
}

export async function uploadBackupChunks(file, manifest, putChunk, { received = [], signal, onProgress = () => {}, maximumBytes } = {}) {
  const plan = validateBackupManifest(manifest, maximumBytes);
  stopIfAborted(signal);
  if (file.size !== plan.size) throw new Error('Select the original archive to resume this upload');
  onProgress({ phase: 'verify', completedBytes: 0, totalBytes: plan.size });
  if (await sha256Bytes(await file.arrayBuffer()) !== plan.sha256) throw new Error('Selected archive differs from the staged upload');
  const known = new Map();
  for (const row of received) {
    if (!Number.isSafeInteger(row.index) || row.index < 0 || row.index >= plan.count || known.has(row.index) || !HASH.test(row.sha256 || ''))
      throw new Error('Invalid resumed-upload metadata');
    known.set(row.index, row);
  }
  let completed = 0;
  for (let index = 0; index < plan.count; index++) {
    stopIfAborted(signal);
    const part = new Uint8Array(await file.slice(index * plan.chunk, Math.min((index + 1) * plan.chunk, plan.size)).arrayBuffer());
    const hash = await sha256Bytes(part), prior = known.get(index);
    if (prior && (prior.sha256 !== hash || prior.byte_count !== part.byteLength)) throw new Error('Existing upload chunk does not match the selected archive');
    if (!prior) {
      const receipt = await putChunk(index, part, hash, { signal });
      if (receipt?.sha256 !== hash || receipt?.byte_count !== part.byteLength) throw new Error('Upload acknowledgement mismatch; reload stage status before retrying');
    }
    completed += part.byteLength;
    onProgress({ phase: 'upload', completedBytes: completed, totalBytes: plan.size });
  }
  stopIfAborted(signal);
  onProgress({ phase: 'uploaded', completedBytes: completed, totalBytes: plan.size });
  // Preview and explicit commit are separate caller actions, never automatic.
  return { byte_count: completed, sha256: plan.sha256 };
}

export async function readBackupChunkResponse(response, { signal } = {}) {
  const declared = response.headers.get('Content-Length');
  if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > BACKUP_CHUNK_BYTES))
    throw new Error('Backup chunk response exceeds its transfer limit');
  if (!response.body?.getReader) throw new Error('This browser cannot read bounded backup chunks. Use a native client.');
  const reader = response.body.getReader(), parts = []; let size = 0;
  try {
    while (true) {
      stopIfAborted(signal);
      const value = await reader.read();
      stopIfAborted(signal);
      if (value.done) break;
      size += value.value.byteLength;
      if (size > BACKUP_CHUNK_BYTES) throw new Error('Backup chunk response exceeds its transfer limit');
      parts.push(value.value);
    }
    if (declared !== null && size !== Number(declared)) throw new Error('Backup chunk response was incomplete');
    const bytes = new Uint8Array(size); let offset = 0;
    for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
    return { bytes, sha256: response.headers.get('X-Chunk-SHA256') };
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
