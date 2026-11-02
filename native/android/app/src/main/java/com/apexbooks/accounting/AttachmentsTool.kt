package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.*
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

fun sha256(bytes:ByteArray)=MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)}
fun verifyReceipt(bytes:ByteArray,row:JSONObject){require(bytes.size.toLong()==row.optLong("size_bytes",-1)&&sha256(bytes)==row.s("sha256")){"Receipt checksum or size did not match. The file was not saved."}}
class AttachmentDraft {
    var bytes:ByteArray?=null;var filename by mutableStateOf("");var mediaType=""
    var key=UUID.randomUUID().toString();var unresolved by mutableStateOf(false)
    var update:JSONObject?=null;var attachmentId=""
    fun reset(){bytes=null;filename="";mediaType="";update=null;attachmentId="";unresolved=false;key=UUID.randomUUID().toString()}
    fun failed(e:Exception){if(e is ApiFailure&&e.status in 400..499&&e.status !in setOf(408,409))unresolved=false}
}
@Composable fun AttachmentsTool(vm:AppModel){
    val record=vm.toolData?:return;val cid=vm.companyId;val stamp=remember(cid){vm.workspaceStamp()};val rid=record.s("id");val draft=remember(cid,rid){vm.attachmentDraft(rid)}
    var rows by remember{mutableStateOf(emptyList<JSONObject>())};var storage by remember{mutableStateOf<JSONObject?>(null)};var busy by remember{mutableStateOf(false)};var failure by remember{mutableStateOf("")};var reload by remember{mutableIntStateOf(0)};var showArchived by remember{mutableStateOf(false)}
    val scope=rememberCoroutineScope();val root=vm.api.company(cid)
    suspend fun load(){val result=vm.api.request("$root/records/${encode(rid)}/attachments") as JSONObject;if(vm.inWorkspace(cid,stamp)){rows=result.a("attachments").objects();storage=result.o("storage")}}
    fun act(block:suspend()->Unit){if(busy)return;busy=true;failure="";scope.launch{try{block()}catch(e:Exception){currentCoroutineContext().ensureActive();failure=e.message?:"Receipt operation failed.";if(e is ApiFailure&&e.status==401)vm.failure(e)}finally{busy=false}}}
    fun close(){if(busy||draft.unresolved)return;draft.reset();vm.tool="";vm.detail=record}
    fun submit(){act{
        draft.unresolved=true
        try{if(draft.update!=null)vm.api.request("$root/attachments/${encode(draft.attachmentId)}","PUT",draft.update,draft.key)
            else vm.api.upload("$root/records/${encode(rid)}/attachments?filename=${encode(draft.filename)}","POST",draft.bytes?:error("Choose a receipt first."),draft.mediaType,draft.key)
            draft.reset()
        }catch(e:Exception){draft.failed(e);throw e}
        try{load()}catch(e:Exception){currentCoroutineContext().ensureActive();failure="Receipt saved. Refresh the list; do not upload it again. ${e.message.orEmpty()}"}
    }}
    LaunchedEffect(cid,rid,reload){try{load()}catch(e:Exception){currentCoroutineContext().ensureActive();failure=e.message?:"Could not load retained receipts.";if(e is ApiFailure&&e.status==401)vm.failure(e)}}
    ActionDialog("Retained receipts · ${record.s("number")}",vm,working={busy},unresolved={draft.unresolved},hasChanges={draft.bytes!=null},confirm="Done",onDismiss=::close,onSave={close()}){
        Text("Evidence only: attaching or archiving a receipt never changes posted accounts or stock. Files are not opened or scanned automatically.",style=MaterialTheme.typography.bodySmall)
        if(failure.isNotBlank())Text(failure,color=MaterialTheme.colorScheme.error)
        if(storage==null){Text("Loading receipt list and storage limits…");TextButton(enabled=!busy,onClick={reload++}){Text("Retry list")}}
        storage?.let{limits->
            Text("${limits.optLong("used_bytes")/1024} KiB used / ${limits.optLong("quota_bytes")/1024} KiB · archived files still count",style=MaterialTheme.typography.bodySmall)
            if(vm.canWrite){
                OutlinedButton(enabled=!busy&&!draft.unresolved&&rows.size<limits.optInt("max_files_per_record")&&limits.optLong("remaining_bytes")>0,onClick={vm.files.pick(arrayOf("application/pdf","image/png","image/jpeg")){uri->act{
                    val maximum=minOf(limits.optLong("max_file_bytes"),limits.optLong("remaining_bytes"),2L*1024*1024).toInt();require(maximum>0){"No receipt storage remains."}
                    val bytes=vm.files.read(uri,maximum);val mime=vm.files.mediaType(uri);require(mime in setOf("application/pdf","image/png","image/jpeg")){"Choose a PDF, PNG or JPEG receipt."}
                    draft.reset();draft.bytes=bytes;draft.filename=vm.files.displayName(uri);draft.mediaType=mime
                }}}){Text("Choose receipt · PDF / JPEG / PNG")}
                if(draft.bytes!=null){Field("Receipt filename",draft.filename,{if(!draft.unresolved)draft.filename=it},readOnly=draft.unresolved,maximum=120);Text("${draft.bytes!!.size} bytes · ${draft.mediaType}",style=MaterialTheme.typography.bodySmall)}
                if(draft.unresolved)Text("The previous response was uncertain. Retry the exact original receipt operation before leaving.",color=MaterialTheme.colorScheme.error)
                if(draft.bytes!=null||draft.update!=null)Button(enabled=!busy&&draft.filename.length<=120&&(draft.update!=null||draft.filename.isNotBlank()),onClick=::submit){Text(if(draft.unresolved)"Retry original receipt operation" else if(draft.update!=null)"Retry receipt change" else "Upload receipt")}
            }
        }
        Toggle("Show archived receipts",showArchived,{showArchived=it})
        if(rows.isEmpty()&&storage!=null)Text("No retained receipts yet.")
        rows.filter{showArchived||!it.optBoolean("is_archived")}.forEach{row->Section(row.s("filename")){
            Text("${row.optLong("size_bytes")} bytes · ${if(row.optBoolean("is_archived"))"Archived · retained" else "Active"}",style=MaterialTheme.typography.bodySmall)
            Text(row.s("created_at"),style=MaterialTheme.typography.bodySmall)
            OutlinedButton(enabled=!busy&&!draft.unresolved,onClick={act{val bytes=vm.api.rawBytes("$root/attachments/${encode(row.s("id"))}/download",maximumResponse=2*1024*1024);verifyReceipt(bytes,row);if(vm.inWorkspace(cid,stamp))vm.files.save(bytes,row.s("filename"))}}){Text("Download / save file")}
            if(vm.canWrite)TextButton(enabled=!busy&&!draft.unresolved&&draft.bytes==null,onClick={draft.reset();draft.attachmentId=row.s("id");draft.update=JSONObject().put("version",row.optInt("version")).put("is_archived",!row.optBoolean("is_archived"));submit()}){Text(if(row.optBoolean("is_archived"))"Reactivate receipt" else "Archive · retain evidence")}
        }}
        TextButton(enabled=!busy&&!draft.unresolved,onClick={reload++}){Text("Refresh receipt list")}
    }
}
