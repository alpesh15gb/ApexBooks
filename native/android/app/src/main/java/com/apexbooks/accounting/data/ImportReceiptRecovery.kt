package com.apexbooks.accounting.data

import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.UUID

/** Durable opaque reference only. CSV bodies live in the open editor, never on disk. */
class ImportReceiptRecovery(private val file:File) {
    data class Marker(val key:String,val kind:String,val hash:String)
    data class Attempt(val key:String?,val body:String,val retry:Boolean)
    companion object {
        private val storageGate=Any()
        fun hash(value:String)=MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8)).joinToString(""){"%02x".format(it)}
        fun location(folder:File,origin:String,account:String,company:String,bank:Boolean=false):File {
            require(account.isNotBlank()&&company.isNotBlank()){ "Sign in and select a company before importing." }
            return File(File(folder,if(bank)"bank-import-recovery"else"import-recovery"),hash(listOf(origin,account.trim().lowercase(),company).joinToString("\n"))+".ref")
        }
    }
    private fun read():Marker? {
        if(!file.exists())return null
        require(file.length()<=512){"Import recovery reference is damaged; verify the original import before continuing."}
        val parts=file.readText(Charsets.UTF_8).split('\n')
        require(parts.size==3&&parts[0].matches(Regex("[a-f0-9-]{36}"))&&parts[1] in setOf("party","item","bank")&&parts[2].matches(Regex("[a-f0-9]{64}"))){"Import recovery reference is damaged; verify the original import before continuing."}
        return Marker(parts[0],parts[1],parts[2])
    }
    var marker:Marker?=read();private set
    var busy=false;private set
    val pending get()=marker!=null
    private fun <T> locked(block:()->T):T = synchronized(storageGate) {
        file.parentFile?.mkdirs()
        FileOutputStream(File(file.path+".lock"),true).channel.use { channel ->
            channel.lock().use { block() }
        }
    }
    fun begin(body:String,kind:String,supported:Boolean):Attempt =
        if(supported)locked{beginLocked(body,kind,true)}else beginLocked(body,kind,false)
    private fun beginLocked(body:String,kind:String,supported:Boolean):Attempt {
        check(!busy){"An import request is already in progress."}
        val disk=read()
        check(disk==null||marker==null||disk.key==marker?.key){"Another import reference exists. Verify the original operations before continuing."}
        val existing=disk?:marker;marker=existing
        if(!supported){check(existing==null){"Reconnect to a server supporting import receipts to recover this import."};busy=true;return Attempt(null,body,false)}
        require(kind in setOf("party","item","bank"))
        val digest=hash(body)
        if(existing!=null)check(existing.kind==kind&&existing.hash==digest){"Select the original CSV, bank, mapping and import type without changes to retry the original operation."}
        val value=existing?:Marker(UUID.randomUUID().toString(),kind,digest)
        if(disk==null){
            file.parentFile?.mkdirs()
            val temporary=File.createTempFile("import-", ".tmp",file.parentFile)
            try { FileOutputStream(temporary).use{output->output.write(listOf(value.key,value.kind,value.hash).joinToString("\n").toByteArray(Charsets.UTF_8));output.fd.sync()};Files.move(temporary.toPath(),file.toPath(),StandardCopyOption.ATOMIC_MOVE) }
            finally { temporary.delete() }
            check(read()==value){"Could not retain import recovery reference; no import was sent."}
        }
        marker=value;busy=true;return Attempt(value.key,body,existing!=null)
    }
    fun confirmed(key:String) = locked {
        val saved=read()?:throw IllegalStateException("Import recovery reference is missing; verify the original result.")
        check(saved.key==key&&marker?.key==key){"Unexpected import receipt; the original import remains unresolved."}
        check(file.delete()){ "Import confirmed, but recovery reference could not be cleared. Check its receipt again." }
        marker=null
    }
    fun failed(attempt:Attempt,status:Int) {
        if(attempt.key!=null&&!attempt.retry&&status in 400..499&&status !in setOf(408,409))confirmed(attempt.key)
    }
    fun end(){busy=false}
}
