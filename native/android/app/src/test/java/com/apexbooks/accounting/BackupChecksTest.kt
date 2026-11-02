package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApiFailure
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class BackupChecksTest {
    private fun metadata(size:Long=600000)=JSONObject().put("byte_count",size).put("chunk_size",524288).put("chunk_count",(size+524287)/524288).put("sha256","a".repeat(64)).put("state","ready")
    @Test fun transferMetadataRejectsWrongBoundaries(){BackupChecks.metadata(metadata(),1000000);for(value in listOf(metadata().put("chunk_size",600000),metadata().put("chunk_count",1),metadata().put("state","expired"),metadata().put("sha256","bad"),metadata(1000001))){assertThrows(IllegalArgumentException::class.java){BackupChecks.metadata(value,1000000)}}}
    @Test fun chunksAndAcknowledgementsMustMatchExactBytes(){val bytes=ByteArray(8){it.toByte()};BackupChecks.part(bytes,1,524296,sha256(bytes));assertThrows(IllegalArgumentException::class.java){BackupChecks.part(bytes,1,524297,sha256(bytes))};val ack=JSONObject().put("received",true).put("index",1).put("size_bytes",8).put("sha256",sha256(bytes));BackupChecks.ack(ack,bytes,1);assertThrows(IllegalArgumentException::class.java){BackupChecks.ack(ack.put("size_bytes",7),bytes,1)}}
    @Test fun receiptsCannotSaveTamperedOrTruncatedBytes(){val bytes="synthetic receipt".toByteArray();val metadata=JSONObject().put("size_bytes",bytes.size).put("sha256",sha256(bytes));verifyReceipt(bytes,metadata);assertThrows(IllegalArgumentException::class.java){verifyReceipt(bytes+1.toByte(),metadata)}}
    @Test fun uncertainReceiptRetainsPayloadKeyUntilKnown(){val draft=AttachmentDraft();draft.bytes="original".toByteArray();val key=draft.key;draft.unresolved=true;draft.failed(ApiFailure(0,"timeout"));assertTrue(draft.unresolved);assertEquals(key,draft.key);assertEquals("original",draft.bytes!!.toString(Charsets.UTF_8));draft.failed(ApiFailure(422,"invalid"));assertFalse(draft.unresolved);draft.reset();assertNull(draft.bytes);assertNotEquals(key,draft.key)}
}
