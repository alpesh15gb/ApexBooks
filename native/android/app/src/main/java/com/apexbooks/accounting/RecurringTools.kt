package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import java.time.LocalDate
import java.time.Instant
import java.time.ZoneOffset
import java.util.UUID

/** Recurring routes guarantee every 409 is a definite rollback, unlike generic financial routes. */
class RecurringCommand {
    private val pending=RetrySubmission()
    var key:String=UUID.randomUUID().toString();private set
    var unresolved by mutableStateOf(false);private set
    fun body(value:JSONObject)=pending.body(value)
    fun succeeded(){pending.succeeded();unresolved=false}
    fun failed(error:Exception){
        if(error is ApiFailure&&error.status==409)pending.succeeded()else pending.failed(error)
        unresolved=pending.unresolved;if(!unresolved)key=UUID.randomUUID().toString()
    }
}
fun recurringBusinessDate(instant:Instant=Instant.now())=instant.atOffset(ZoneOffset.ofHoursMinutes(5,30)).toLocalDate().toString()

fun recurringScheduleIssue(name:String,start:String,frequency:String,interval:String,end:String):String? {
    if(name.isBlank()||name.length>120)return "Enter a schedule name of up to 120 characters."
    if(frequency !in setOf("weekly","monthly")||interval.toIntOrNull() !in 1..12)return "Choose weekly or monthly, with an interval from 1 to 12."
    val first=runCatching{LocalDate.parse(start)}.getOrNull()?:return "Choose a valid start date."
    if(end.isNotBlank()){val last=runCatching{LocalDate.parse(end)}.getOrNull()?:return "Choose a valid end date.";if(last<first)return "End date cannot be before the start date."}
    return null
}
private suspend fun recurringWrite(vm:AppModel,command:RecurringCommand,path:String,method:String,body:JSONObject,validate:(JSONObject)->Unit={}):JSONObject {
    try{return (vm.api.request(path,method,command.body(body),command.key)as JSONObject).also{validate(it);command.succeeded()}}
    catch(e:Exception){command.failed(e);throw e}
}
@Composable private fun RecurringPending(command:RecurringCommand){if(command.unresolved)Message("The previous request may already have completed. Retry original request to recover the same template or draft. Original values and key are retained; closing is blocked until its outcome is known.")}

@Composable fun RecurringTools(vm:AppModel){val row=vm.toolData?:JSONObject();when(vm.tool){
    "recurring_new"->RecurringCreate(vm,row)
    "recurring_edit"->key(row.s("id"),row.optInt("version")){RecurringEdit(vm,row)}
    "recurring_occurrence"->RecurringOccurrence(vm,row)
    "recurring_review"->RecurringReview(vm,row)
    else->RecurringHub(vm)
}}
@Composable private fun RecurringHub(vm:AppModel){
    val cid=vm.companyId;val stamp=vm.workspaceStamp();var revision by remember{mutableIntStateOf(0)}
    var rows by remember{mutableStateOf<List<JSONObject>?>(null)};var failure by remember{mutableStateOf("")};var mode by remember{mutableStateOf("due")};var search by remember{mutableStateOf("")}
    var dueIds by remember{mutableStateOf(emptySet<String>())};var businessDate by remember{mutableStateOf("")};var timezone by remember{mutableStateOf("")}
    LaunchedEffect(cid,revision){rows=null;failure="";try{
        val (all,due)=coroutineScope{val all=async{vm.api.request(vm.api.company(cid,"/recurring-templates"))as JSONObject};val due=async{vm.api.request(vm.api.company(cid,"/recurring-templates/due"))as JSONObject};all.await() to due.await()}
        if(vm.inWorkspace(cid,stamp)){rows=all.a("templates").objects();dueIds=due.a("rows").objects().map{it.s("id")}.toSet();businessDate=due.s("business_date").ifBlank{due.s("as_of")};timezone=due.s("timezone")}
    }catch(e:Exception){currentCoroutineContext().ensureActive();failure=e.message?:"Could not load schedules.";if(e is ApiFailure&&e.status==401)vm.failure(e)}}
    ActionDialog("Recurring draft schedules",vm,confirm="Done",onSave={vm.tool=""},onDismiss={vm.tool=""}){
        Text("Create each scheduled draft explicitly, then review or convert it. Schedules never post invoices, move stock, charge customers or run automatically.")
        if(businessDate.isNotBlank())Text("Business date $businessDate · $timezone",style=MaterialTheme.typography.bodySmall)
        Choice("Show",mode,listOf("due" to "Due now","all" to "All schedules","paused" to "Paused"),{mode=it})
        Field("Find schedule or party",search,{search=it})
        TextButton(onClick={revision++}){Text("Refresh schedules")}
        if(failure.isNotBlank())Message(failure,true)
        if(rows==null&&failure.isBlank())LinearProgressIndicator(Modifier.fillMaxWidth())
        val visible=rows.orEmpty().filter{(it.s("name")+" "+it.s("party_name")).contains(search.trim(),true)}.filter{when(mode){"due"->it.s("id")in dueIds;"paused"->!it.optBoolean("is_active");else->true}}
        if(rows!=null&&visible.isEmpty())Text("No matching schedules. Open a saved estimate, proforma, sales order or purchase order and choose Create recurring draft schedule.")
        for(row in visible)Section(row.s("name")){
            Text("${friendly(row.s("draft_kind"))} · ${row.s("party_name")}");Text("Every ${row.s("interval")} ${if(row.s("frequency")=="weekly")"week(s)"else"month(s)"} · ${if(row.optBoolean("is_active"))"Active"else"Paused"}",style=MaterialTheme.typography.bodySmall)
            DetailValue("Next scheduled date",row.s("next_due").ifBlank{"Complete / no remaining dates"});DetailValue("Drafts generated",row.s("generated_count"))
            OutlinedButton(onClick={vm.task{val result=vm.api.request(vm.api.company(cid,"/recurring-templates/${encode(row.s("id"))}"))as JSONObject;if(vm.inWorkspace(cid,stamp)){vm.toolData=result;vm.tool="recurring_edit"}}}){Text(if(vm.canWrite)"Manage / pause schedule"else"View schedule")}
            if(vm.canWrite){
                if(row.optBoolean("is_active")&&row.s("id")in dueIds)Button(onClick={vm.toolData=row;vm.tool="recurring_occurrence"}){Text("Create next due draft")}
            }else Text("Read-only access · an owner or editor can manage or create drafts.",style=MaterialTheme.typography.bodySmall)
        }
    }
}
@Composable private fun RecurringCreate(vm:AppModel,source:JSONObject){
    val cid=vm.companyId;val stamp=vm.workspaceStamp();val scope="new:${source.s("id")}";val command=remember(cid,scope){vm.recurringCommand(scope)}
    var name by remember{mutableStateOf((friendly(source.s("kind"))+" · "+source.s("name")).take(120))};var start by remember{mutableStateOf(recurringBusinessDate())};var frequency by remember{mutableStateOf("monthly")};var interval by remember{mutableStateOf("1")};var end by remember{mutableStateOf("")}
    val baseline=remember{listOf(name,start,frequency,interval,end)}
    ActionDialog("Create recurring draft schedule",vm,enabled=vm.canWrite,confirm=if(command.unresolved)"Retry original request"else"Create schedule",unresolved={command.unresolved},hasChanges={listOf(name,start,frequency,interval,end)!=baseline},onDismiss={vm.finishRecurring(scope);vm.tool="";vm.toolData=null},onSave={
        if(!command.unresolved)recurringScheduleIssue(name,start,frequency,interval,end)?.let{throw Exception(it)}
        if(!vm.inWorkspace(cid,stamp))return@ActionDialog
        recurringWrite(vm,command,vm.api.company(cid,"/recurring-templates"),"POST",JSONObject().put("name",name).put("source_record_id",source.s("id")).put("start_date",start).put("frequency",frequency).put("interval",interval.toIntOrNull()?:1).put("end_date",end.ifBlank{null}?:JSONObject.NULL).put("is_active",true))
        if(vm.inWorkspace(cid,stamp)){vm.finishRecurring(scope);vm.tool="recurring";vm.toolData=null;vm.notice="Schedule saved. Each occurrence still needs an explicit Create draft and review."}
    }){
        RecurringPending(command);Text("Source: ${source.s("number")} · ${source.s("name")}. The API saves a draft snapshot; existing documents are not changed.")
        Field("Schedule name",name,{name=it},maximum=120);DateField("First scheduled date",start,{start=it});Choice("Frequency",frequency,listOf("weekly" to "Weekly","monthly" to "Monthly"),{frequency=it});Field("Interval · 1 to 12",interval,{interval=it},number=true,maximum=2);DateField("End date · optional",end,{end=it},optional=true)
        Text("Schedule dates and cadence cannot be edited after creation. Pause and create a replacement to change them. Monthly schedules keep the original day, clamping short months.",style=MaterialTheme.typography.bodySmall)
    }
}
@Composable private fun RecurringEdit(vm:AppModel,row:JSONObject){
    val cid=vm.companyId;val stamp=vm.workspaceStamp();val scope="edit:${row.s("id")}";val command=remember(cid,scope){vm.recurringCommand(scope)}
    var name by remember{mutableStateOf(row.s("name"))};var active by remember{mutableStateOf(row.optBoolean("is_active"))};var source by remember{mutableStateOf("")}
    val options=vm.records.filter{it.s("kind")==row.s("draft_kind")&&it.s("converted_to").isBlank()}
    fun changed()=name!=row.s("name")||active!=row.optBoolean("is_active")||source.isNotBlank()
    fun close(){if(!vm.inWorkspace(cid,stamp)||vm.tool!="recurring_edit"||vm.toolData!==row)return;check(!command.unresolved){"The previous save may already have completed. Restore editor access and retry the original request before closing."};vm.finishRecurring(scope);vm.toolData=null;vm.tool="recurring"}
    ActionDialog("Manage recurring schedule",vm,enabled=vm.canWrite||(!command.unresolved&&!changed()),confirm=if(!vm.canWrite)"Done"else if(command.unresolved)"Retry original request"else"Save schedule",unresolved={command.unresolved},hasChanges=::changed,onDismiss=::close,onSave={
        if(!vm.inWorkspace(cid,stamp)||vm.tool!="recurring_edit"||vm.toolData!==row)return@ActionDialog
        if(!vm.canWrite){check(!command.unresolved&&!changed()){"Read-only access: your draft and any unresolved request are preserved. Restore editor access to retry or save; do not create a replacement."};close();return@ActionDialog}
        if(!command.unresolved)require(name.isNotBlank()&&name.length<=120){"Enter a schedule name of up to 120 characters."}
        val body=JSONObject().put("version",row.optInt("version")).put("name",name).put("is_active",active);if(source.isNotBlank())body.put("source_record_id",source)
        recurringWrite(vm,command,vm.api.company(cid,"/recurring-templates/${encode(row.s("id"))}"),"PUT",body)
        if(vm.inWorkspace(cid,stamp)){close();vm.notice="Future schedule settings updated; previously generated drafts are unchanged."}
    }){
        if(!vm.canWrite&&(command.unresolved||changed()))Text("Read-only access: your inputs are preserved. Restore editor access to retry the original request or save. An unresolved result must be recovered before closing.")
        RecurringPending(command);Field("Schedule name",name,{name=it},maximum=120,readOnly=!vm.canWrite);Toggle("Active · available to create due drafts",active,{active=it},enabled=vm.canWrite);Text("Start ${row.s("start_date")} · every ${row.s("interval")} ${row.s("frequency")} · end ${row.s("end_date").ifBlank{"none"}}",style=MaterialTheme.typography.bodySmall)
        Text("Cadence is immutable. Pause this schedule and create another to change dates or frequency.")
        Choice("Future draft snapshot",source,listOf("" to "Keep current saved snapshot")+options.map{it.s("id")to "${it.s("number")} · ${it.s("name")}"},{source=it},enabled=vm.canWrite)
        Text("Choosing a source explicitly replaces only the future draft snapshot; already generated drafts are retained.",style=MaterialTheme.typography.bodySmall)
        Section("Saved future draft snapshot"){Text(row.o("draft").s("name"));for(line in row.o("draft").o("data").a("lines").objects().take(100))Text("${line.s("description")} · ${line.s("quantity")} × ${money(line.s("rate"))}",style=MaterialTheme.typography.bodySmall)}
        TextButton(enabled=!command.unresolved&&vm.busy==0,onClick={vm.task{val fresh=vm.api.request(vm.api.company(cid,"/recurring-templates/${encode(row.s("id"))}"))as JSONObject;if(vm.inWorkspace(cid,stamp)){if(fresh.optInt("version")!=row.optInt("version"))vm.finishRecurring(scope);name=fresh.s("name");active=fresh.optBoolean("is_active");source="";vm.toolData=fresh}}}){Text("Reload latest schedule")}
    }
}
@Composable private fun RecurringOccurrence(vm:AppModel,row:JSONObject){
    val cid=vm.companyId;val stamp=vm.workspaceStamp();val occurrence=row.s("next_due");val scope="occurrence:${row.s("id")}:$occurrence";val command=remember(cid,scope){vm.recurringCommand(scope)}
    ActionDialog("Create and review scheduled draft",vm,enabled=vm.canWrite&&vm.recordsReady,confirm=if(command.unresolved)"Retry original request"else"Create draft for $occurrence",unresolved={command.unresolved},onDismiss={vm.finishRecurring(scope);vm.toolData=null;vm.tool="recurring"},onSave={
        check(vm.canWrite&&vm.inWorkspace(cid,stamp)){"Current editor or owner access is required to generate a draft. Your original request is preserved."}
        val result=recurringWrite(vm,command,vm.api.company(cid,"/recurring-templates/${encode(row.s("id"))}/occurrences"),"POST",JSONObject().put("occurrence_date",occurrence)){response->val draft=response.o("record");if(draft.s("id").isBlank()||draft.s("kind") !in vm.draftKinds)throw ApiFailure(502,"The server did not identify the generated draft. Retry the original request to recover it.")}
        if(vm.inWorkspace(cid,stamp)){vm.finishRecurring(scope);vm.toolData=result.o("record");vm.tool="recurring_review";reviewGeneratedRecurringDraft(vm)}
    }){RecurringPending(command);Text(row.s("name"));DetailValue("Occurrence date",occurrence);Text("Creates only the earliest due draft. Repeating this same occurrence returns that existing draft, not a duplicate. Review it before converting to an invoice or bill.")}
}

/** Confirmed draft recovery performs reads only; generation retries remain in RecurringCommand. */
suspend fun reviewGeneratedRecurringDraft(vm:AppModel){
    val saved=vm.toolData?:return;val id=vm.companyId;val stamp=vm.workspaceStamp();val page=vm.page;val session=vm.api.captureSession()
    val recordId=saved.s("id");val reference=saved.s("number").ifBlank{recordId}
    fun current()=vm.inWorkspace(id,stamp)&&vm.page==page&&vm.tool=="recurring_review"&&vm.toolData===saved&&runCatching{session();true}.getOrDefault(false)
    if(!current())return
    try{
        vm.refresh();if(!current()||!vm.recordsReady)return
        val access=vm.readStamp();val fresh=vm.api.record(id,recordId)
        if(!current()||!vm.canRead(id,access))return
        if(fresh.s("id")!=recordId||fresh.s("kind") !in vm.draftKinds)throw ApiFailure(409,"The saved record needs review in the document list.")
        val next=if(vm.canWrite&&!fresh.optBoolean("cancelled")&&fresh.s("converted_to").isBlank())EntryEditor(vm,fresh.s("kind"),previous=fresh)else null
        vm.editor=next;vm.detail=if(next==null)fresh else null;vm.tool="";vm.toolData=null
        vm.notice="Scheduled draft $reference is saved. Review before converting; no invoice or stock posting has occurred."
    }catch(e:Exception){
        if(e is kotlinx.coroutines.CancellationException)throw e
        if(current()||(vm.inWorkspace(id,stamp)&&vm.tool=="recurring_review"&&vm.toolData===saved&&!vm.api.signedIn))throw ApiFailure((e as? ApiFailure)?.status?:0,"Draft $reference is saved. Refresh/open failed. Do not generate another occurrence; retry opening this saved draft or find it in the document list. ${e.message.orEmpty()}")
    }
}
@Composable private fun RecurringReview(vm:AppModel,row:JSONObject){
    val cid=vm.companyId;val stamp=vm.workspaceStamp()
    ActionDialog("Scheduled draft saved · review pending",vm,confirm="Refresh and open saved draft",enabled=vm.signedIn,working={vm.busy>0},onDismiss={vm.tool="";vm.toolData=null},onSave={
        if(vm.inWorkspace(cid,stamp)&&vm.tool=="recurring_review"&&vm.toolData===row)reviewGeneratedRecurringDraft(vm)
    }){
        Text("Draft ${row.s("number").ifBlank{row.s("id")}} is saved. No invoice or stock posting occurred.")
        Text("Do not generate another occurrence to recover it. Refresh and open only reads company data and this saved draft. You can cancel and find it later in its document list.")
    }
}
