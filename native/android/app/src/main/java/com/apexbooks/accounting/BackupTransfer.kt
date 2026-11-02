package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.File
import java.io.RandomAccessFile
import java.security.MessageDigest

object BackupChecks {
    const val CHUNK=524288
    fun hash(file:File):String {val digest=MessageDigest.getInstance("SHA-256");file.inputStream().use{input->val buffer=ByteArray(65536);while(true){if(Thread.currentThread().isInterrupted)throw java.io.InterruptedIOException("Cancelled");val n=input.read(buffer);if(n<0)break;digest.update(buffer,0,n)}};return digest.digest().joinToString(""){"%02x".format(it)}}
    fun metadata(value:JSONObject,maximum:Long){val size=value.optLong("byte_count",-1);require(size in 1..maximum&&value.optInt("chunk_size")==CHUNK&&value.optInt("chunk_count")==((size+CHUNK-1)/CHUNK).toInt()&&value.s("sha256").matches(Regex("[a-f0-9]{64}"))){"Invalid or oversized backup transfer metadata."};require(value.s("state") !in setOf("expired","cancelled")){"This transfer expired or was cancelled. Start a new transfer explicitly."}}
    fun size(total:Long,index:Int)=minOf(CHUNK.toLong(),total-index.toLong()*CHUNK).toInt().also{require(it>0)}
    fun part(bytes:ByteArray,index:Int,total:Long,hash:String){require(bytes.size==size(total,index)&&sha256(bytes)==hash){"Backup chunk $index failed size/checksum verification."}}
    fun ack(value:JSONObject,bytes:ByteArray,index:Int){require(value.optBoolean("received")&&value.optInt("index",-1)==index&&value.optInt("size_bytes",-1)==bytes.size&&value.s("sha256")==sha256(bytes)){"The server did not acknowledge the exact backup chunk."}}
}
class BackupTransfer(private val api:ApexApi){
    suspend fun exportFile(company:String,stage:JSONObject,file:File,maximum:Long,progress:(String)->Unit)=withContext(Dispatchers.IO){
        BackupChecks.metadata(stage,maximum);val chunks=stage.a("chunks").objects().associateBy{it.optInt("index",-1)};require(chunks.size==stage.optInt("chunk_count")){"Export snapshot has missing chunks."}
        val total=stage.optLong("byte_count");val digest=MessageDigest.getInstance("SHA-256")
        try{file.outputStream().use{out->for(index in 0 until stage.optInt("chunk_count")){currentCoroutineContext().ensureActive();progress("Downloading chunk ${index+1} of ${stage.optInt("chunk_count")}");val metadata=chunks[index]?:error("Missing chunk");val bytes=api.rawBytes(api.company(company,"/backup-exports/${encode(stage.s("export_id"))}/chunks/$index"),maximumResponse=BackupChecks.CHUNK);BackupChecks.part(bytes,index,total,metadata.s("sha256"));require(metadata.optInt("size_bytes")==bytes.size){"Export chunk size differs from its manifest."};out.write(bytes);digest.update(bytes)}};val hash=digest.digest().joinToString(""){"%02x".format(it)};require(file.length()==total&&hash==stage.s("sha256")){"Whole backup checksum mismatch. File was not offered for saving."}}catch(e:Exception){file.delete();throw e}
    }
    suspend fun uploadFile(stage:JSONObject,file:File,maximum:Long,progress:(String)->Unit):JSONObject=withContext(Dispatchers.IO){
        BackupChecks.metadata(stage,maximum);require(file.length()==stage.optLong("byte_count")&&BackupChecks.hash(file)==stage.s("sha256")){"Select the exact original backup file to resume this transfer."}
        val id=stage.s("upload_id");val received=stage.a("chunks").objects().associateBy{it.optInt("index",-1)};val total=file.length()
        RandomAccessFile(file,"r").use{input->for(index in 0 until stage.optInt("chunk_count")){currentCoroutineContext().ensureActive();val bytes=ByteArray(BackupChecks.size(total,index));input.seek(index.toLong()*BackupChecks.CHUNK);input.readFully(bytes);progress("Uploading chunk ${index+1} of ${stage.optInt("chunk_count")}");val old=received[index];if(old!=null){BackupChecks.part(bytes,index,total,old.s("sha256"));require(old.optInt("size_bytes")==bytes.size){"Previously received chunk has a different size."}}else{val ack=api.upload("/api/backups/uploads/${encode(id)}/chunks/$index","PUT",bytes,"application/octet-stream");BackupChecks.ack(ack,bytes,index)}}}
        val preview=api.request("/api/backups/uploads/${encode(id)}/preview","POST")as JSONObject;require(preview.s("digest")==stage.s("sha256")){"Preview digest differs from the selected backup."};preview
    }
}
