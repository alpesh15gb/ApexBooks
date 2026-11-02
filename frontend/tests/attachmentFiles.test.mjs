import test from 'node:test';
import assert from 'node:assert/strict';
import {validateReceiptFile,validateReceiptSignature,verifiedReceiptDownload,receiptDigest,safeReceiptFilename,MAX_RECEIPT_BYTES} from '../src/attachmentFiles.js';
const bytes=new TextEncoder().encode('%PDF-1.4\nsynthetic\n%%EOF');
test('receipt prevalidation rejects size, type and path before file reads',()=>{
 for(const file of [{size:MAX_RECEIPT_BYTES+1,name:'a.pdf',type:'application/pdf'},{size:0,name:'a.pdf',type:'application/pdf'},{size:1,name:'a.svg',type:'image/svg+xml'},{size:1,name:'../a.pdf',type:'application/pdf'}])assert.throws(()=>validateReceiptFile(file));
 assert.deepEqual(validateReceiptFile({size:bytes.length,name:'Bill.pdf',type:'application/pdf'}),{filename:'Bill.pdf',mediaType:'application/pdf'});
 assert.throws(()=>validateReceiptSignature(bytes,'image/png'),/do not match/);validateReceiptSignature(bytes,'application/pdf');
});
test('download verifies length/checksum and yields forced-download MIME only',async()=>{
 const row={size_bytes:bytes.length,sha256:await receiptDigest(bytes)};
 const blob=await verifiedReceiptDownload(new Response(bytes,{headers:{'Content-Length':String(bytes.length),'X-Content-SHA256':row.sha256}}),row);
 assert.equal(blob.type,'application/octet-stream');assert.deepEqual(new Uint8Array(await blob.arrayBuffer()),bytes);
 await assert.rejects(verifiedReceiptDownload(new Response(bytes.subarray(1)),row),/incomplete/);
 await assert.rejects(verifiedReceiptDownload(new Response(new Uint8Array(bytes.length)),row),/checksum mismatch/);
 await assert.rejects(verifiedReceiptDownload(new Response(new Uint8Array(bytes.length+1)),row),/declared size/);
 assert.equal(safeReceiptFilename('../bad\n.pdf'),'.._bad_.pdf');
});
