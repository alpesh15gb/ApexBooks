import test from 'node:test';
import assert from 'node:assert/strict';
import { pbkdf2Sync, createCipheriv, createDecipheriv } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import { encryptPortableBackup, readPortableBackup, MAX_BACKUP_PLAINTEXT_BYTES, MAX_ENCRYPTED_BACKUP_BYTES } from '../src/portableBackup.js';
const password = 'Synthetic-password-only';
const json = new TextEncoder().encode('{"format":"apex-company-backup","version":7}');
function independentEnvelope(content) {
  const salt = Buffer.alloc(16, 255), iv = Buffer.alloc(12, 255);
  const cipher = createCipheriv('aes-256-gcm', pbkdf2Sync(password, salt, 250000, 32, 'sha256'), iv);
  const ciphertext = Buffer.concat([cipher.update(content), cipher.final(), cipher.getAuthTag()]);
  // Deliberately unlike web property order; escaped slashes and Unicode escapes
  // are valid output from JSON writers and must not be parsed by string slicing.
  return JSON.stringify({ ciphertext: ciphertext.toString('base64'), iv: iv.toString('base64'), version: 1, salt: salt.toString('base64'), format: 'apex-encrypted-backup' }).replaceAll('/', '\\/').replace('apex', '\\u0061pex');
}
const bytes = s => new TextEncoder().encode(s);
test('independent AES-GCM writer fixtures decrypt gzip, legacy JSON and v8 ZIP transport', async () => {
  for (const [kind, content] of [['json', json], ['gzip', gzipSync(json)], ['zip', Buffer.from([80,75,3,4,0,0,0,0])]]) {
    const restored = await readPortableBackup(bytes(independentEnvelope(content)), password);
    assert.equal(restored.kind, kind); assert.equal(restored.encrypted, true);
    assert.deepEqual(Buffer.from(restored.content), Buffer.from(content));
  }
});
test('web writer remains readable with independent native-compatible parameters', async () => {
  const encoded = await encryptPortableBackup(json, password);
  const envelope = JSON.parse(new TextDecoder().decode(encoded));
  assert.equal(envelope.version, 1);
  const cipher = Buffer.from(envelope.ciphertext, 'base64');
  const decipher = createDecipheriv('aes-256-gcm', pbkdf2Sync(password, Buffer.from(envelope.salt,'base64'),250000,32,'sha256'), Buffer.from(envelope.iv,'base64'));
  decipher.setAuthTag(cipher.subarray(-16));
  assert.deepEqual(Buffer.concat([decipher.update(cipher.subarray(0,-16)),decipher.final()]),Buffer.from(json));
  const second = await encryptPortableBackup(json,password);
  assert.notDeepEqual(encoded,second,'fresh salt and IV each encryption');
});
test('legacy plaintext JSON/gzip and ZIP recognized without mutation', async () => {
  for (const content of [json,gzipSync(json),Buffer.from([80,75,5,6])]) {
    const result = await readPortableBackup(new Blob([content]));
    assert.equal(result.encrypted,false); assert.deepEqual(Buffer.from(result.content),Buffer.from(content));
  }
});
test('wrong password, authenticated tamper and truncation have controlled errors', async () => {
  const encoded = bytes(independentEnvelope(json));
  await assert.rejects(readPortableBackup(encoded,'incorrect password'),/incorrect.*damaged/);
  const envelope=JSON.parse(new TextDecoder().decode(encoded));
  const c=Buffer.from(envelope.ciphertext,'base64');c[0]^=1;envelope.ciphertext=c.toString('base64');
  await assert.rejects(readPortableBackup(bytes(JSON.stringify(envelope)),password),/incorrect.*damaged/);
  await assert.rejects(readPortableBackup(encoded.subarray(0,-8),password),/Invalid backup/);
});
test('metadata and version rejected before deriving key', async () => {
  const original=JSON.parse(independentEnvelope(json));
  for(const patch of [{salt:'x'},{iv:'AAAA'},{ciphertext:'%%%%'},{ciphertext:'A==='},{version:2}])
    await assert.rejects(readPortableBackup(bytes(JSON.stringify({...original,...patch})),password),/Invalid encrypted|Unsupported/);
  await assert.rejects(encryptPortableBackup(json,'short'),/at least 12/);
});
test('oversized buffers/files refuse before read/crypto and never fall back', async () => {
  assert.equal(MAX_BACKUP_PLAINTEXT_BYTES, 8 * 1024 * 1024);
  assert.equal(MAX_ENCRYPTED_BACKUP_BYTES, 12 * 1024 * 1024);
  await assert.rejects(encryptPortableBackup(new Uint8Array(MAX_BACKUP_PLAINTEXT_BYTES+1),password),/native client/);
  const file = new Blob([new Uint8Array(MAX_ENCRYPTED_BACKUP_BYTES+1)]);
  file.arrayBuffer=()=>{throw Error('must not read');};
  await assert.rejects(readPortableBackup(file,password),/native client/);
});
test('cancellation before work and during PBKDF2 does not return a backup', async () => {
  const before=new AbortController();before.abort();
  await assert.rejects(encryptPortableBackup(json,password,{signal:before.signal}),{name:'AbortError'});
  const during=new AbortController();
  const pending=encryptPortableBackup(json,password,{signal:during.signal});
  setTimeout(()=>during.abort(),5);
  await assert.rejects(pending,{name:'AbortError'});
});
