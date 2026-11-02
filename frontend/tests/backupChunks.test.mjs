import test from 'node:test';
import assert from 'node:assert/strict';
import { BACKUP_CHUNK_BYTES, MAX_WEB_ARCHIVE_BYTES, sha256Bytes, validateBackupManifest, downloadBackupChunks, uploadBackupChunks, readBackupChunkResponse } from '../src/backupChunks.js';
async function fixture() {
 const bytes=Uint8Array.from({length:BACKUP_CHUNK_BYTES*2+23},(_,index)=>index%251),file=new Blob([bytes]);
 const manifest={byte_count:bytes.length,sha256:await sha256Bytes(bytes),chunk_size:BACKUP_CHUNK_BYTES,chunk_count:3};
 const chunks=await Promise.all([0,1,2].map(async index=>{const part=bytes.slice(index*BACKUP_CHUNK_BYTES,(index+1)*BACKUP_CHUNK_BYTES);return{index,bytes:part,sha256:await sha256Bytes(part),byte_count:part.length};}));
 manifest.chunks=chunks.map(({index,sha256,byte_count})=>({index,sha256,byte_count}));return{bytes,file,manifest,chunks};
}
test('download verifies checksums and assembles bounded independent chunks',async()=>{
 const {bytes,manifest,chunks}=await fixture();const progress=[];
 const archive=await downloadBackupChunks(manifest,async index=>chunks[index],{onProgress:value=>progress.push(value)});
 assert.deepEqual(new Uint8Array(await archive.arrayBuffer()),bytes);assert.equal(progress.at(-1).phase,'complete');assert.equal(progress.at(-1).completedBytes,bytes.length);
 assert.ok(chunks.every(row=>row.byte_count<=512*1024));
});
test('corruption, incomplete chunk and changed complete archive checksum never produce a backup',async()=>{
 const {manifest,chunks}=await fixture();
 await assert.rejects(downloadBackupChunks(manifest,async index=>({...chunks[index],sha256:'0'.repeat(64)})),/checksum/);
 await assert.rejects(downloadBackupChunks(manifest,async index=>({...chunks[index],bytes:chunks[index].bytes.slice(1)})),/length/);
 await assert.rejects(downloadBackupChunks({...manifest,sha256:'0'.repeat(64)},async index=>chunks[index]),/Complete archive checksum/);
});
test('resumed upload verifies existing chunks and sends only missing bytes without committing restore',async()=>{
 const {file,manifest,chunks}=await fixture();const sent=[];
 const result=await uploadBackupChunks(file,manifest,async(index,part,hash)=>{sent.push(index);assert.ok(part.length<=512*1024);return{sha256:hash,byte_count:part.length};},{received:[manifest.chunks[0]]});
 assert.deepEqual(sent,[1,2]);assert.equal(result.sha256,manifest.sha256);
 await assert.rejects(uploadBackupChunks(file,manifest,()=>assert.fail(),{received:[{...manifest.chunks[0],sha256:'0'.repeat(64)}]}),/does not match/);
 assert.equal(chunks[2].byte_count,23);
});
test('wrong file, oversized manifests and cancellation stop before writing',async()=>{
 const {file,manifest}=await fixture();
 assert.throws(()=>validateBackupManifest({...manifest,byte_count:MAX_WEB_ARCHIVE_BYTES+1}),/browser transfer limit/);
 assert.throws(()=>validateBackupManifest({...manifest,chunk_count:4}),/manifest/);
 await assert.rejects(uploadBackupChunks(new Blob(['wrong']),manifest,()=>assert.fail()),/original archive/);
 const controller=new AbortController();controller.abort();
 await assert.rejects(uploadBackupChunks(file,manifest,()=>assert.fail(),{signal:controller.signal}),{name:'AbortError'});
});

test('mobile buffered path explicitly refuses 64 MiB before fetching any data',async()=>{
 const size=64*1024*1024;
 await assert.rejects(downloadBackupChunks({byte_count:size,chunk_size:BACKUP_CHUNK_BYTES,chunk_count:size/BACKUP_CHUNK_BYTES,sha256:'0'.repeat(64)},()=>assert.fail('must not download oversized backup')),/native client.*no files will be omitted/);
});
test('mid-transfer cancellation and expired authentication stop without completing or committing',async()=>{
 const {file,manifest,chunks}=await fixture();
 const downloadAbort=new AbortController();const phases=[];let fetched=0;
 await assert.rejects(downloadBackupChunks(manifest,async index=>{fetched++;return chunks[index];},{signal:downloadAbort.signal,onProgress:event=>{phases.push(event.phase);if(event.phase==='download')downloadAbort.abort();}}),{name:'AbortError'});
 assert.equal(fetched,1);assert.ok(!phases.includes('complete'));
 const uploadAbort=new AbortController();let sent=0;
 await assert.rejects(uploadBackupChunks(file,manifest,async(index,part,hash)=>{sent++;uploadAbort.abort();return{sha256:hash,byte_count:part.byteLength};},{signal:uploadAbort.signal}),{name:'AbortError'});
 assert.equal(sent,1);
 const denied=Object.assign(new Error('Sign in again'),{status:401});
 await assert.rejects(downloadBackupChunks(manifest,async()=>{throw denied;}),error=>error===denied);
 await assert.rejects(uploadBackupChunks(file,manifest,async()=>{throw denied;}),error=>error===denied);
});

test('binary download rejects oversized or truncated responses before concatenating unbounded bytes',async()=>{
 const response=new Response(new Uint8Array(BACKUP_CHUNK_BYTES+1));
 await assert.rejects(readBackupChunkResponse(response),/transfer limit/);
 await assert.rejects(readBackupChunkResponse(new Response('x',{headers:{'Content-Length':'900000000'}})),/transfer limit/);
 await assert.rejects(readBackupChunkResponse(new Response('x',{headers:{'Content-Length':'2'}})),/incomplete/);
 const result=await readBackupChunkResponse(new Response('abc',{headers:{'Content-Length':'3','X-Chunk-SHA256':'0'.repeat(64)}}));
 assert.deepEqual([...result.bytes],[97,98,99]);
});
