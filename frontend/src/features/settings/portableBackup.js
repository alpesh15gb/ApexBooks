// Portable v1 envelope: shared with existing web, Android and Windows writers.
// WebCrypto is whole-buffer: this is intentionally not a streaming codec.
// This codec has a tighter bound than the separate 16 MiB plain chunk transport.
export const MAX_BACKUP_PLAINTEXT_BYTES = 8 * 1024 * 1024;
export const MAX_ENCRYPTED_BACKUP_BYTES = 12 * 1024 * 1024;
const MAX_CIPHERTEXT_BYTES = MAX_BACKUP_PLAINTEXT_BYTES + 16;
const FORMAT = "apex-encrypted-backup";
const oversized = () => new Error("Backup is too large for browser encryption (8 MiB plaintext / 12 MiB encrypted file). Use a native client for the complete archive; no unencrypted fallback was created.");
function checkpoint(signal) {
  if (signal?.aborted) throw new DOMException("Backup operation cancelled", "AbortError");
}
function asBytes(value) {
  if (value instanceof Uint8Array) return value;
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  throw new Error("Backup content must be bytes");
}
function encode64(value) {
  const parts = [];
  // Chunk boundaries are multiples of three: only the final chunk is padded.
  for (let i = 0; i < value.length; i += 24576)
    parts.push(btoa(String.fromCharCode(...value.subarray(i, i + 24576))));
  return parts.join("");
}
function decode64(value, min, max) {
  if (typeof value !== "string" || value.length > Math.ceil(max / 3) * 4 ||
      (value.length % 4 !== 0 || /[^A-Za-z0-9+/=]/.test(value) || value.slice(0, -2).includes("=") || /=[^=]/.test(value)))
    throw new Error("Invalid encrypted backup metadata");
  const length = value.length / 4 * 3 - (value.endsWith("==") ? 2 : value.endsWith("=") ? 1 : 0);
  if (length < min || length > max) throw new Error("Invalid encrypted backup metadata");
  const raw = atob(value);
  const decoded = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) decoded[i] = raw.charCodeAt(i);
  return decoded;
}
async function keyFor(password, salt, signal) {
  checkpoint(signal);
  const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
  checkpoint(signal);
  const key = await crypto.subtle.deriveKey({ name: "PBKDF2", salt, iterations: 250000, hash: "SHA-256" }, material, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  checkpoint(signal);
  return key;
}
export async function encryptPortableBackup(input, password, { signal } = {}) {
  checkpoint(signal);
  const bytes = asBytes(input);
  if (bytes.byteLength > MAX_BACKUP_PLAINTEXT_BYTES) throw oversized();
  if (typeof password !== "string" || password.length < 12)
    throw new Error("Use a backup password of at least 12 characters");
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await keyFor(password, salt, signal);
  const ciphertext = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, bytes));
  checkpoint(signal);
  const envelope = JSON.stringify({ format: FORMAT, version: 1, salt: encode64(salt), iv: encode64(iv), ciphertext: encode64(ciphertext) });
  checkpoint(signal);
  return new TextEncoder().encode(envelope);
}
// Classifies transport only. ZIP contents/version and JSON schema remain the restore
// validator's responsibility. Never decompress an untrusted archive in this codec.
export function backupPayloadKind(input) {
  const bytes = asBytes(input);
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) return "gzip";
  if (bytes[0] === 0x50 && bytes[1] === 0x4b &&
      ((bytes[2] === 3 && bytes[3] === 4) || (bytes[2] === 5 && bytes[3] === 6))) return "zip";
  try {
    const object = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (object && typeof object === "object" && !Array.isArray(object)) return "json";
  } catch { /* Controlled invalid-file result below. */ }
  throw new Error("Invalid backup file: expected ZIP, gzip or JSON");
}
export async function readPortableBackup(input, password = "", { signal } = {}) {
  checkpoint(signal);
  const size = input instanceof Blob ? input.size : asBytes(input).byteLength;
  if (size > MAX_ENCRYPTED_BACKUP_BYTES) throw oversized();
  let content = input instanceof Blob ? new Uint8Array(await input.arrayBuffer()) : asBytes(input);
  checkpoint(signal);
  let encrypted = false;
  // Binary formats bypass JSON parsing, but still obey plaintext bounds.
  if (content[0] !== 0x1f && content[0] !== 0x50) {
    let envelope;
    try { envelope = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(content)); }
    catch { throw new Error("Invalid backup file"); }
    if (envelope?.format === FORMAT) {
      if (envelope.version !== 1) throw new Error("Unsupported encrypted backup version");
      const salt = decode64(envelope.salt, 16, 16);
      const iv = decode64(envelope.iv, 12, 12);
      const ciphertext = decode64(envelope.ciphertext, 16, MAX_CIPHERTEXT_BYTES);
      if (typeof password !== "string" || !password) throw new Error("Enter the password used to encrypt this backup");
      try {
        const key = await keyFor(password, salt, signal);
        content = new Uint8Array(await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ciphertext));
      } catch (error) {
        if (error.name === "AbortError") throw error;
        throw new Error("The password is incorrect or the encrypted backup is damaged");
      }
      checkpoint(signal);
      encrypted = true;
    }
  }
  if (content.byteLength > MAX_BACKUP_PLAINTEXT_BYTES) throw oversized();
  checkpoint(signal);
  const kind = backupPayloadKind(content);
  checkpoint(signal);
  return { content, kind, encrypted };
}
