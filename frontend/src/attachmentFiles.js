export const MAX_RECEIPT_BYTES = 2 * 1024 * 1024;
const TYPES = new Set(['application/pdf', 'image/png', 'image/jpeg']);
export function validateReceiptFile(file) {
  if (!file || !Number.isSafeInteger(file.size) || file.size < 1 || file.size > MAX_RECEIPT_BYTES)
    throw new Error('Choose a non-empty receipt of at most 2 MiB.');
  if (!TYPES.has(file.type)) throw new Error('Only PDF, PNG and JPEG receipts are supported.');
  if (!file.name || file.name.length > 120 || /[\\/\x00-\x1f\x7f]/.test(file.name))
    throw new Error('Use a filename of at most 120 characters without paths or control characters.');
  return { filename: file.name, mediaType: file.type };
}
export function validateReceiptSignature(bytes, type) {
  const matches = expected => expected.every((value, i) => bytes[i] === value);
  const valid = type === 'image/png' ? matches([137,80,78,71,13,10,26,10]) : type === 'image/jpeg' ? matches([255,216,255]) : type === 'application/pdf' && /^%PDF-[12]\.\d\s/.test(new TextDecoder().decode(bytes.subarray(0,16)));
  if (!valid) throw new Error('Receipt bytes do not match the selected PDF, PNG or JPEG type.');
}
export async function receiptDigest(bytes) {
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2,'0')).join('');
}
export async function verifiedReceiptDownload(response, attachment) {
  if (!Number.isSafeInteger(attachment.size_bytes) || attachment.size_bytes < 1 || attachment.size_bytes > MAX_RECEIPT_BYTES || !/^[a-f0-9]{64}$/.test(attachment.sha256 || '')) throw new Error('Invalid receipt download metadata.');
  const declared = response.headers.get('Content-Length');
  if (declared !== null && Number(declared) !== attachment.size_bytes) throw new Error('Receipt download length mismatch. Nothing was saved.');
  const headerHash = response.headers.get('X-Content-SHA256');
  if (headerHash && headerHash !== attachment.sha256) throw new Error('Receipt checksum changed. Reload the receipt list.');
  // Read bounded network chunks; do not allocate an unlimited server response.
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Receipt download streaming is unavailable in this browser.');
  const chunks = []; let length = 0;
  try {
    while (true) {
      const {done,value} = await reader.read(); if (done) break;
      length += value.byteLength;
      if (length > attachment.size_bytes) throw new Error('Receipt exceeds its declared size. Nothing was saved.');
      chunks.push(value);
    }
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  if (length !== attachment.size_bytes) throw new Error('Receipt download is incomplete. Nothing was saved.');
  const bytes = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk,offset); offset += chunk.byteLength; }
  if (await receiptDigest(bytes) !== attachment.sha256) throw new Error('Receipt checksum mismatch. Nothing was saved.');
  // No preview/inline rendering: even valid signatures are not a malware scan.
  return new Blob([bytes], {type:'application/octet-stream'});
}
export function safeReceiptFilename(name) {
  return String(name || 'receipt').replace(/[\\/\x00-\x1f\x7f]/g,'_').slice(0,120) || 'receipt';
}
