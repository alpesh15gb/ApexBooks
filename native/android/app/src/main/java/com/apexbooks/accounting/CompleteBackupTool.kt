package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import com.apexbooks.backup.BackupFormat
import com.apexbooks.backup.StreamingEncryptedBackup
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.File
import java.util.UUID

class CompleteBackupDraft {
    var stage by mutableStateOf<JSONObject?>(null);var preview by mutableStateOf<JSONObject?>(null)
    var file by mutableStateOf<File?>(null);var protectedFile:StreamingEncryptedBackup.PrivateFile?=null
    var selectedName by mutableStateOf("");var kind by mutableStateOf<BackupFormat.Kind?>(null)
    var targetName by mutableStateOf("");var password by mutableStateOf("");var encrypt by mutableStateOf(true)
    var busy by mutableStateOf(false);var awaitingPicker by mutableStateOf(false);var pending by mutableStateOf("")
    var progress by mutableStateOf("");var problem by mutableStateOf("");var completedCompany by mutableStateOf("")
    var key=UUID.randomUUID().toString();var creation:JSONObject?=null
    fun localCleanup(){protectedFile?.close();protectedFile=null;file?.delete();file=null;kind=null;selectedName="";password=""}
    fun reset(){check(pending.isBlank()){ "Recover the original transfer outcome first." };localCleanup();stage=null;preview=null;creation=null;key=UUID.randomUUID().toString();completedCompany="";progress="";problem=""}
    fun failed(e:Exception){if(e is ApiFailure&&e.status in 400..499&&e.status !in setOf(408,409)){pending=""}}
}
@Composable fun CompleteBackupTool(vm:AppModel){
    val importing=vm.tool=="restore";val cid=vm.companyId;val stamp=remember(cid){vm.workspaceStamp()};val state=remember(cid,importing){vm.backupDraft(if(importing)"import" else "export:$cid")}
    val scope=rememberCoroutineScope();val transfer=remember{BackupTransfer(vm.api)}
    var recoveries by remember{mutableStateOf(emptyList<JSONObject>())};var showRecovery by remember{mutableStateOf(false)}
    val maximum=minOf(vm.capabilityLimits["backup_archive_max_bytes"]?:0,StreamingEncryptedBackup.MAX_PLAIN_BYTES)
    val jsonMaximum=minOf(vm.capabilityLimits["backup_company_json_max_bytes"]?:0,50_000_000)
    fun act(block:suspend()->Unit){if(state.busy||state.awaitingPicker)return;state.busy=true;state.problem="";scope.launch{try{block()}catch(e:Exception){currentCoroutineContext().ensureActive();state.problem=e.message?:"Backup operation failed.";if(e is ApiFailure&&e.status==410){state.pending="";state.stage?.put("state","expired");state.preview=null;state.problem="This retained transfer expired. Check your existing companies before starting another restore; no existing company was deleted."};if(e is ApiFailure&&e.status==401)vm.failure(e)}finally{state.busy=false}}}
    suspend fun listRecovery(){val result=vm.api.request("/api/backups/transfers") as JSONObject;recoveries=result.a("transfers").objects();showRecovery=true}
    suspend fun stageStatus(stage:JSONObject):JSONObject=vm.api.request(if(stage.s("export_id").isNotBlank())vm.api.company(stage.s("source_company_id").ifBlank{cid},"/backup-exports/${encode(stage.s("export_id"))}")else"/api/backups/uploads/${encode(stage.s("upload_id"))}")as JSONObject
    fun close(){if(state.busy||state.awaitingPicker||state.pending.isNotBlank())return;state.localCleanup();vm.tool=""}
    suspend fun prepareImport(){
        val selected=state.file?:error("Choose a portable backup first.");val job=currentCoroutineContext()[Job]
        if(state.kind==BackupFormat.Kind.ENCRYPTED_V1){require(state.password.isNotEmpty()){ "Enter the backup password. It stays on this device." };state.progress="Authenticating encrypted backup locally…";val pass=state.password.toCharArray();val decoded=try{withContext(Dispatchers.IO){selected.inputStream().use{StreamingEncryptedBackup.decrypt(it,pass,vm.files.privateStaging,maximum){job?.isActive==false}}}}finally{pass.fill('\u0000')}
            val detected=try{withContext(Dispatchers.IO){BackupFormat.inspect(decoded.file(),jsonMaximum)}}catch(e:Exception){decoded.close();throw e};require(detected!=BackupFormat.Kind.ENCRYPTED_V1){decoded.close();"Nested encrypted backups are not supported."};selected.delete();state.protectedFile=decoded;state.file=decoded.file();state.kind=detected;state.password=""
        }
        val file=state.file?:error("The private backup file is unavailable.");require(file.length() in 1..maximum){"Backup exceeds this server's archive limit."}
        val hash=withContext(Dispatchers.IO){BackupChecks.hash(file)}
        if(state.stage==null){require(state.targetName.trim().length in 1..120){"Enter a new company name (1–120 characters)."};if(state.creation==null)state.creation=JSONObject().put("company_name",state.targetName.trim()).put("byte_count",file.length()).put("sha256",hash);state.pending="begin_import"
            try{state.stage=vm.api.request("/api/backups/uploads","POST",state.creation,state.key)as JSONObject;state.pending=""}catch(e:Exception){state.failed(e);throw e}
        }
        val stage=stageStatus(state.stage!!);state.stage=stage;require(stage.s("sha256")==hash&&stage.optLong("byte_count")==file.length()){ "Select the exact original file for this retained transfer." };state.targetName=stage.s("target_company_name")
        if(stage.s("company_id").isNotBlank()){state.completedCompany=stage.s("company_id");state.pending="";state.progress="This transfer was already restored. Open the existing company; do not restore it again.";return}
        state.preview=transfer.uploadFile(stage,file,maximum){state.progress=it};state.progress="Validated preview ready. No company has been created yet."
    }
    fun export(){act{try{
        require(maximum>0&&jsonMaximum>0){"Server backup limits are unavailable. Retry the feature check."}
        if(state.encrypt)require(state.password.length>=12){"Use an encryption password of at least 12 characters."}
        if(state.stage==null){state.pending="begin_export";state.progress="Creating immutable company and receipt snapshot…";try{state.stage=vm.api.request(vm.api.company(cid,"/backup-exports"),"POST",JSONObject(),state.key)as JSONObject;state.pending=""}catch(e:Exception){state.failed(e);throw e}}
        val stage=stageStatus(state.stage!!);state.stage=stage;BackupChecks.metadata(stage,maximum)
        state.localCleanupForDownload()
        val raw=withContext(Dispatchers.IO){java.nio.file.Files.createTempFile(vm.files.privateStaging.toPath(),"export-",".part").toFile()};state.file=raw
        transfer.exportFile(cid,stage,raw,maximum){state.progress=it}
        if(state.encrypt){state.progress="Encrypting verified backup locally…";val pass=state.password.toCharArray();val job=currentCoroutineContext()[Job];val protected=try{withContext(Dispatchers.IO){raw.inputStream().use{StreamingEncryptedBackup.encrypt(it,pass,vm.files.privateStaging,maximum){job?.isActive==false}}}}finally{pass.fill('\u0000')};raw.delete();state.protectedFile=protected;state.file=protected.file();state.kind=BackupFormat.Kind.ENCRYPTED_V1;state.password=""}else state.kind=BackupFormat.Kind.ZIP_ARCHIVE
        state.progress="Complete backup verified and ready to save. It includes archived receipts."
    }catch(e:Exception){state.localCleanupForDownload();throw e}}}
    fun commit(){act{
        val stage=state.stage?:error("No import transfer selected.");val preview=state.preview?:error("Validate the backup preview first.");require(preview.s("digest")==stage.s("sha256")){"Preview does not match this transfer."};state.pending="commit";state.progress="Restoring into a new company…"
        val result=try{vm.api.request("/api/backups/uploads/${encode(stage.s("upload_id"))}/commit","POST",JSONObject().put("digest",preview.s("digest")))as JSONObject}catch(e:Exception){state.failed(e);throw e}
        require(result.s("company_id").isNotBlank()){ "Restore response was incomplete. Retry the same transfer to recover its outcome." };state.completedCompany=result.s("company_id");state.pending="";state.progress="Restore completed. Existing companies were not overwritten.";state.localCleanup()
    }}
    ActionDialog(if(importing)"Restore complete portable backup" else "Complete company backup",vm,working={state.busy||state.awaitingPicker},unresolved={state.pending.isNotBlank()},confirm="Done",onDismiss=::close,onSave={close()}){
        Text(if(importing)"Restore creates a NEW company only after you validate and confirm. Passwords never leave this device." else "Includes all company records and retained receipts, even archived files. The snapshot is immutable; no production books are changed.",style=MaterialTheme.typography.bodySmall)
        if(state.problem.isNotBlank())Text(state.problem,color=MaterialTheme.colorScheme.error)
        if(state.progress.isNotBlank())Text(state.progress,style=MaterialTheme.typography.bodyMedium)
        if(state.busy)LinearProgressIndicator(Modifier.fillMaxWidth())
        if(maximum<=0||jsonMaximum<=0){Text("The server did not provide required backup byte limits.");TextButton(onClick={vm.retryCapabilities()}){Text("Retry feature check")}}
        else {
            Text("Archive limit ${maximum/1024/1024} MiB · bounded 512 KiB transfers",style=MaterialTheme.typography.bodySmall)
            if(importing){
                Field("New company name",state.targetName,{if(state.stage==null&&state.pending.isBlank()){state.targetName=it;state.creation=null;state.key=UUID.randomUUID().toString()}},readOnly=state.stage!=null||state.pending.isNotBlank()||state.busy,maximum=120)
                OutlinedButton(enabled=!state.busy&&state.pending.isBlank()&&state.completedCompany.isBlank(),onClick={vm.files.pick{uri->act{
                    state.localCleanup();if(state.stage==null){state.creation=null;state.key=UUID.randomUUID().toString()};state.preview=null;state.progress="Reading selected backup into private staging…";val selected=vm.files.stage(uri,((maximum+18)/3)*4*6+16384)
                    try{val kind=withContext(Dispatchers.IO){BackupFormat.inspect(selected,jsonMaximum)};state.file=selected;state.kind=kind;state.selectedName=vm.files.displayName(uri);state.progress=if(kind==BackupFormat.Kind.ENCRYPTED_V1)"Encrypted backup detected. Authenticate locally before any upload."else"${friendly(kind.name)} selected. Server preview will validate the archive format and schema."}catch(e:Exception){selected.delete();throw e}
                }}}){Text(if(state.file==null)"Choose backup file" else "Choose another file")}
                if(state.selectedName.isNotBlank())Text(state.selectedName)
                if(state.kind==BackupFormat.Kind.ENCRYPTED_V1)Field("Backup password · local only",state.password,{state.password=it},password=true,readOnly=state.busy,maximum=128)
                if(state.file!=null&&state.completedCompany.isBlank())Button(enabled=!state.busy&&state.pending!="commit",onClick={act{prepareImport()}}){Text(if(state.pending=="begin_import")"Retry original transfer creation" else if(state.stage==null)"Authenticate, upload & validate" else "Resume upload & validate")}
                state.preview?.let{preview->Section("Review before creating the new company"){
                    DetailValue("New company",state.stage?.s("target_company_name").orEmpty());DetailValue("Backup schema",preview.s("schema_version"));DetailValue("Retained receipts",preview.s("attachment_count"));DetailValue("Receipt bytes",preview.s("attachment_bytes"));ReportContent(preview)
                    Button(enabled=!state.busy&&state.completedCompany.isBlank(),onClick=::commit){Text(if(state.pending=="commit")"Retry the SAME restore" else "Confirm restore into new company")}
                }}
                if(state.completedCompany.isNotBlank())TextButton(enabled=!state.busy,onClick={state.reset()}){Text("Start a different restore")}
                if(state.completedCompany.isNotBlank())Button(enabled=!state.busy&&vm.busy==0,onClick={if(vm.busy==0){val id=state.completedCompany;vm.task{vm.loadCompanies(id);if(vm.signedIn&&vm.companyId==id&&vm.recordsReady)vm.notice="Restored company opened. No existing company was overwritten."}}}){Text("Open restored company")}
            }else{
                Toggle("Encrypt saved backup",state.encrypt,{if(!state.busy&&state.pending.isBlank()&&state.file==null)state.encrypt=it},enabled=!state.busy&&state.pending.isBlank()&&state.file==null)
                if(state.encrypt&&state.file==null)Field("Encryption password · at least 12 characters",state.password,{state.password=it},password=true,readOnly=state.busy||state.pending.isNotBlank(),maximum=128)
                if(!state.encrypt)Text("Unencrypted ZIP: anyone with this file can read company records and receipts. This is an explicit unencrypted export.",color=MaterialTheme.colorScheme.error)
                if(state.file==null)Button(enabled=!state.busy,onClick=::export){Text(if(state.pending=="begin_export")"Retry original snapshot creation" else if(state.stage!=null)"Resume complete export" else "Prepare complete backup")}
                else Button(enabled=!state.busy&&!state.awaitingPicker&&state.progress.startsWith("Complete backup verified"),onClick={state.awaitingPicker=true;vm.files.saveFile(state.file!!,"apex-complete-${cid.take(8)}-${today()}."+if(state.kind==BackupFormat.Kind.ENCRYPTED_V1)"apexbackup"else"zip"){saved->state.awaitingPicker=false;state.progress=if(saved)"Complete backup verified and saved to your selected location."else"Complete backup verified. Save was cancelled or failed; you can try again."}}){Text("Save verified backup file")}
            }
            if(state.pending.isNotBlank())Text("The last response is uncertain. Recover or retry the original transfer; do not start a duplicate restore.",color=MaterialTheme.colorScheme.error)
            if(state.stage?.s("state") in setOf("expired","cancelled")&&state.pending.isBlank())TextButton(enabled=!state.busy,onClick={state.reset()}){Text("Clear expired transfer and start again")}
            TextButton(enabled=!state.busy,onClick={act{listRecovery()}}){Text("Find retained transfers / recover interrupted work")}
            if(showRecovery){if(recoveries.isEmpty())Text("No retained transfers were returned by this account.");recoveries.forEach{row->Section("${friendly(row.s("direction"))} · ${row.s("target_company_name").ifBlank{row.s("source_company_id").take(8)}}"){
                Text("${row.optLong("byte_count")} bytes · ${row.s("state")} · expires ${row.s("expires_at")}",style=MaterialTheme.typography.bodySmall)
                val sameMode=if(importing)row.s("direction")=="import"else row.s("direction")=="export"&&row.s("source_company_id")==cid
                if(sameMode)OutlinedButton(enabled=!state.busy,onClick={act{
                    if(state.pending=="commit"){require(row.s("upload_id")==state.stage?.s("upload_id")){"Recover the same restore transfer first."};val latest=stageStatus(row);state.stage=latest;if(latest.s("company_id").isNotBlank()){state.completedCompany=latest.s("company_id");state.pending="";state.progress="The original restore completed. Open the existing company."}else state.progress="The restore outcome is not confirmed. Retry the SAME restore using the retained digest.";showRecovery=false;return@act}
                    if(state.pending=="begin_import")require(row.s("sha256")==state.creation?.s("sha256")&&row.s("target_company_name")==state.creation?.s("company_name")){"This is not the original pending import."}
                    state.localCleanup();state.stage=row;state.preview=null;state.pending="";state.creation=null;state.key=UUID.randomUUID().toString();state.targetName=row.s("target_company_name");state.completedCompany=row.s("company_id");state.progress=if(state.completedCompany.isNotBlank())"This transfer already restored a company. Open it rather than importing again."else if(importing)"Select the exact original backup file to resume this retained transfer."else"Retained snapshot selected. Enter encryption settings and resume export.";showRecovery=false
                }}){Text(if(row.s("company_id").isNotBlank())"Recover restored company" else "Resume this transfer")}
                if(state.pending.isBlank())TextButton(enabled=!state.busy&&row.s("state")!="restored",onClick={act{val path=if(row.s("direction")=="export")vm.api.company(row.s("source_company_id"),"/backup-exports/${encode(row.s("export_id"))}")else"/api/backups/uploads/${encode(row.s("upload_id"))}";val cancelled=vm.api.request(path,"DELETE")as JSONObject;if(!cancelled.optBoolean("cancelled")){val latest=stageStatus(row);if(latest.s("company_id").isNotBlank()){state.stage=latest;state.completedCompany=latest.s("company_id");state.progress="This restore already completed. Cancellation did not delete the company."};listRecovery();return@act};if(row.s("upload_id").isNotBlank()&&row.s("upload_id")==state.stage?.s("upload_id")||row.s("export_id").isNotBlank()&&row.s("export_id")==state.stage?.s("export_id"))state.reset();listRecovery()}}){Text("Cancel staging only · never deletes books")}
            }}}
        }
    }
}
private fun CompleteBackupDraft.localCleanupForDownload(){protectedFile?.close();protectedFile=null;file?.delete();file=null;kind=null}
