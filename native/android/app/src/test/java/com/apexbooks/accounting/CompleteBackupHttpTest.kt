package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.net.URI
import java.util.UUID

/** Opt-in isolated loopback only. Never defaults to a hosted endpoint or existing account. */
class CompleteBackupHttpTest {
    @Test fun retainedReceiptCompleteBackupRestoresExactlyOnce()=runBlocking {
        val origin=System.getenv("APEX_SYNTHETIC_API_ORIGIN");assumeTrue("Set explicit isolated loopback API for HTTP acceptance",!origin.isNullOrBlank())
        val uri=URI(origin!!);require(uri.scheme=="http"&&uri.host in setOf("127.0.0.1","localhost","::1")&&uri.userInfo==null&&uri.query==null&&uri.fragment==null&&uri.path in setOf("","/")){"Only isolated loopback HTTP is allowed"}
        val api=ApexApi(origin.trimEnd('/'));val email="android-complete-${UUID.randomUUID()}@example.invalid";val password="Synthetic-Android-Transfer-Only-42!"
        api.request("/api/auth/register","POST",JSONObject().put("email",email).put("password",password));api.login(email,password,false)
        val features=ApiCapabilities.fetch{api.request("/api/capabilities")as JSONObject};assertTrue("chunked_backups" in features&&"document_attachments" in features)
        val company=api.request("/api/companies","POST",JSONObject().put("name","Android synthetic complete backup").put("tax_mode","unregistered").put("state_code","27"))as JSONObject;val cid=company.s("id");val root=api.company(cid)
        val fixed=api.saveRecord(cid,JSONObject("""{"kind":"estimate","name":"Synthetic fixed-discount buyer","date":"2026-04-02","data":{"lines":[{"description":"Fixed discounted item","quantity":1,"rate":100,"gst_rate":0,"discount_amount":10}]}}"""),UUID.randomUUID().toString())
        assertEquals(0,fixed.decimal("amount").compareTo(java.math.BigDecimal("90")))
        val line=LineState(fixed.o("data").a("lines").getJSONObject(0));line.set("description","Only description changed")
        val edited=JSONObject(fixed.toString());edited.o("data").put("lines",org.json.JSONArray().put(line.json())).put("notes","Nonfinancial edit")
        val saved=api.saveRecord(cid,edited,UUID.randomUUID().toString(),fixed);assertEquals(0,saved.decimal("amount").compareTo(java.math.BigDecimal("90")))
        val inclusive=JSONObject("""{"kind":"purchase_order","name":"Synthetic inclusive supplier","date":"2026-04-02","data":{"supplier_state":"27","place_of_supply":"27","document_discount_percent":10,"lines":[{"description":"Inclusive fixed discount","quantity":1,"rate":118,"gst_rate":18,"price_includes_tax":true,"discount_amount":10,"itc_treatment":"ineligible"}]}}""")
        val prepared=api.request("$root/documents/preview","POST",inclusive)as JSONObject;assertEquals(0,prepared.decimal("amount").compareTo(java.math.BigDecimal("97.20")))
        val inclusiveLine=LineState(prepared.o("data").a("lines").getJSONObject(0));inclusive.o("data").put("lines",org.json.JSONArray().put(inclusiveLine.json()))
        assertEquals(0,(api.request("$root/documents/preview","POST",inclusive)as JSONObject).decimal("amount").compareTo(java.math.BigDecimal("97.20")))
        println("PASS ANDROID FIXED DISCOUNT: API draft90 survives reopen/edit/save; inclusive plus document discount remains97.20")
        val record=api.saveRecord(cid,JSONObject("""{"kind":"purchase_bill","name":"Synthetic supplier","date":"2026-04-02","data":{"lines":[{"description":"Synthetic supplies","quantity":1,"rate":100,"gst_rate":0}]}}"""),UUID.randomUUID().toString())
        val random=ByteArray(600000);java.security.SecureRandom().nextBytes(random);val bytes="%PDF-1.4\n% Synthetic transfer receipt\n".toByteArray()+random+"\n%%EOF\n".toByteArray();val path="$root/records/${record.s("id")}/attachments?filename=synthetic.pdf";val key=UUID.randomUUID().toString()
        val receipt=api.upload(path,"POST",bytes,"application/pdf",key).o("attachment");assertEquals(receipt.s("id"),api.upload(path,"POST",bytes,"application/pdf",key).o("attachment").s("id"))
        api.request("$root/attachments/${receipt.s("id")}","PUT",JSONObject().put("version",receipt.optInt("version")).put("is_archived",true),UUID.randomUUID().toString())
        val stage=api.request("$root/backup-exports","POST",JSONObject(),UUID.randomUUID().toString())as JSONObject;val file=File.createTempFile("apex-synthetic-transfer-",".zip")
        try{
            BackupTransfer(api).exportFile(cid,stage,file,128L*1024*1024){};assertTrue(file.length()>BackupChecks.CHUNK)
            val upload=api.request("/api/backups/uploads","POST",JSONObject().put("company_name","Android restored synthetic backup").put("byte_count",file.length()).put("sha256",BackupChecks.hash(file)),UUID.randomUUID().toString())as JSONObject
            val preview=BackupTransfer(api).uploadFile(upload,file,128L*1024*1024){};assertEquals(1,preview.optInt("attachment_count"))
            val commitPath="/api/backups/uploads/${upload.s("upload_id")}/commit";val body=JSONObject().put("digest",preview.s("digest"));val result=api.request(commitPath,"POST",body)as JSONObject;assertEquals(result.s("company_id"),(api.request(commitPath,"POST",body)as JSONObject).s("company_id"))
            val restored=result.s("company_id");val bill=api.records(restored).single{it.s("kind")=="purchase_bill"};val evidence=(api.request(api.company(restored,"/records/${bill.s("id")}/attachments"))as JSONObject).a("attachments").objects().single();assertTrue(evidence.optBoolean("is_archived"))
            val downloaded=api.rawBytes(api.company(restored,"/attachments/${evidence.s("id")}/download"),maximumResponse=2*1024*1024);verifyReceipt(downloaded,evidence);assertArrayEquals(bytes,downloaded)
            val recovery=(api.request("/api/backups/transfers")as JSONObject).a("transfers").objects();assertTrue(recovery.any{it.s("upload_id")==upload.s("upload_id")&&it.s("company_id")==restored})
            println("PASS ANDROID LIVE HTTP: receipt retry/archive, multichunk hash verification, preview, exact commit replay, archived evidence preservation and completed-stage recovery")
        }finally{file.delete();api.request("$root/backup-exports/${stage.s("export_id")}","DELETE");api.logout()}
    }
}
