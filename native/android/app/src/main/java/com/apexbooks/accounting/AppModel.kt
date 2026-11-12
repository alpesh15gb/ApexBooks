package com.apexbooks.accounting

import android.app.Application
import androidx.compose.runtime.*
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class Feature(val key:String,val title:String,val group:String="",val path:String="",val description:String="")
data class PdfView(val bytes:ByteArray,val name:String,val record:JSONObject?=null,val template:String="")

class AppModel(application:Application):AndroidViewModel(application) {
    val api=ApexApi(BuildConfig.API_ORIGIN,SessionVault(application))
    private val catalog=JSONObject(application.assets.open("features.json").bufferedReader().use{it.readText()})
    val navigation=catalog.a("navigation").objects().map{Feature(it.s("key"),it.s("title"),it.s("group"))}
    val reports=catalog.a("reports").objects().map{Feature(it.s("key"),it.s("title"),it.s("group"),it.s("path").substringBefore("?as_of="),it.s("description"))}
    val documentKinds=setOf("sales_invoice","purchase_bill","estimate","proforma","sales_order","purchase_order","credit_note","debit_note","expense","pos")
    val draftKinds=setOf("estimate","proforma","sales_order","purchase_order")
    var apiVersion by mutableStateOf("unknown");private set
    var apiBuildRevision by mutableStateOf("unknown");private set
    var capabilityLimits by mutableStateOf(emptyMap<String,Long>());private set
    var supportedFeatures by mutableStateOf(emptySet<String>());private set
    private var sessionGeneration=0
    private var capabilitiesLoaded=false
    private var capabilitiesRequest:kotlinx.coroutines.Deferred<CapabilityResult>?=null
    var capabilityChecking by mutableStateOf(false);private set
    var capabilityRetryable by mutableStateOf(false);private set
    val capabilityHint get()=if(capabilityChecking)"Checking optional server features…" else if(capabilityRetryable)"Unable to check server features. Retry the feature check; core accounting remains available." else "This optional setting requires a server upgrade."
    fun retryCapabilities(){if(capabilityChecking)return;capabilitiesLoaded=false;capabilitiesRequest=null;viewModelScope.launch{loadCapabilities()}}
    fun supports(feature:String)=feature in supportedFeatures
    private suspend fun loadCapabilities(){if(capabilitiesLoaded)return;val stamp=sessionGeneration;capabilityChecking=true;val request=capabilitiesRequest?:viewModelScope.async{ApiCapabilities.fetchResult{api.request("/api/capabilities") as JSONObject}}.also{capabilitiesRequest=it};val result=request.await();if(signedIn&&stamp==sessionGeneration){supportedFeatures=result.features;apiVersion=result.apiVersion;apiBuildRevision=result.buildRevision;capabilityLimits=result.limits;capabilityRetryable=result.retryable;capabilityChecking=false;capabilitiesLoaded=true}}
    var signedIn by mutableStateOf(false);private set
    var companies by mutableStateOf(emptyList<JSONObject>());private set
    var company by mutableStateOf(JSONObject());private set
    var records by mutableStateOf(emptyList<JSONObject>());private set
    var recordsReady by mutableStateOf(false);private set
    var banks by mutableStateOf(emptyList<JSONObject>());private set
    var page by mutableStateOf("dashboard");private set
    var revision by mutableIntStateOf(0);private set
    var busy by mutableIntStateOf(0);private set
    var error by mutableStateOf("")
    var notice by mutableStateOf("")
    var editor by mutableStateOf<EntryEditor?>(null)
    var detail by mutableStateOf<JSONObject?>(null)
    var companyForm by mutableStateOf(false)
    var companyEdit by mutableStateOf(false)
    var statement by mutableStateOf<JSONObject?>(null)
    var pdf by mutableStateOf<PdfView?>(null)
    var pdfLoading by mutableStateOf(false);private set
    var pdfError by mutableStateOf("");private set
    var pdfRequestedTemplate by mutableStateOf("");private set
    private var pdfRequest=0
    var tool by mutableStateOf("")
    var toolData by mutableStateOf<JSONObject?>(null)
    private val backupDrafts=mutableMapOf<String,CompleteBackupDraft>()
    fun backupDraft(scope:String)=backupDrafts.getOrPut(scope){CompleteBackupDraft()}
    private val attachmentDrafts=mutableMapOf<String,AttachmentDraft>()
    fun attachmentDraft(recordId:String)=attachmentDrafts.getOrPut(companyId+":"+recordId){AttachmentDraft()}
    private val toolDrafts=ToolDraftStore()
    fun toolDraft(scope:String)=toolDrafts.get(companyId,scope)
    fun finishToolDraft(scope:String)=toolDrafts.remove(companyId,scope)
    private val recurringCommands=mutableMapOf<String,RecurringCommand>()
    fun recurringCommand(scope:String)=recurringCommands.getOrPut(companyId+":"+scope){RecurringCommand()}
    fun finishRecurring(scope:String){recurringCommands.remove(companyId+":"+scope)}
    private val posDrafts=mutableMapOf<String,EntryEditor>()
    val heldSaleCount get()=posDrafts.values.count{it.lines.isNotEmpty()||it.submission.unresolved}
    fun saleDraft():EntryEditor=posDrafts.getOrPut(companyId){EntryEditor(this,"pos").also{it.lines.clear();it.set("name","Walk-in customer")}}
    val files=NativeFiles(application){error=it}
    private var generation=0
    private var companyLoads=0
    private var refreshSequence=0
    private var readEpoch=0
    fun readStamp()=(generation.toLong() shl 32) or readEpoch.toLong()
    fun canRead(id:String,stamp:Long)=signedIn&&recordsReady&&companyId==id&&readStamp()==stamp
    fun workspaceStamp()=generation
    fun inWorkspace(id:String,stamp:Int)=signedIn&&companyId==id&&generation==stamp
    /** Keeps a party or item created from inside an editor (quick-add) selectable until the next refresh. */
    fun rememberMaster(row:JSONObject){if(records.none{it.s("id")==row.s("id")})records=records+row}
    val companyId get()=company.s("id")
    val canWrite get()=signedIn&&recordsReady&&company.s("role") in setOf("owner","editor")
    val isOwner get()=company.s("role")=="owner"
    val regular get()=company.s("tax_mode")=="regular"
    fun title(key:String)=navigation.find{it.key==key}?.title?:friendly(key)
    init { if(api.restore()){signedIn=true;task{loadCompanies()}} }
    fun failure(e:Exception){if(e is kotlinx.coroutines.CancellationException)throw e;notice="";error=e.message?:"The operation could not be completed.";if(e is ApiFailure&&e.status==401&&!api.signedIn)endLocalSession()}
    fun task(action:suspend()->Unit){viewModelScope.launch{busy++;error="";notice="";try{action()}catch(e:Exception){failure(e)}finally{busy--}}}
    suspend fun login(email:String,password:String,remember:Boolean){api.login(email,password,remember);signedIn=true;loadCompanies()}
    suspend fun loadCompanies(preferred:String=companyId){val stamp=generation;val request=++companyLoads;if(!capabilitiesLoaded)viewModelScope.launch{loadCapabilities()};val loaded=(api.request("/api/companies") as JSONArray).objects();if(!signedIn||stamp!=generation||request!=companyLoads)return;companies=loaded;val selected=companies.find{it.s("id")==preferred}?:companies.firstOrNull();if(selected!=null)chooseCompany(selected)else{generation++;refreshSequence++;company=JSONObject();records=emptyList();banks=emptyList();recordsReady=false;editor=null;detail=null;pdf=null;statement=null;tool="";toolData=null;posDrafts.clear();companyForm=true;companyEdit=false}}
    suspend fun chooseCompany(selected:JSONObject){val stamp=++generation;val request=++refreshSequence;company=selected;companyForm=false;tool="";toolData=null;records=emptyList();banks=emptyList();recordsReady=false;editor=null;detail=null;pdf=null;statement=null;coroutineScope{val rows=async{api.records(selected.s("id"))};val accounts=async{(api.request(api.company(selected.s("id"),"/bank-accounts")) as JSONArray).objects()};val loaded=rows.await();val loadedBanks=accounts.await();if(stamp==generation&&request==refreshSequence){records=loaded;banks=loadedBanks;recordsReady=true}}}
    suspend fun refresh(){
        val id=companyId;if(id.isBlank()||!signedIn)return
        val stamp=generation;val request=++refreshSequence
        scopedCoreRefresh(
            first={api.records(id)},second={(api.request(api.company(id,"/bank-accounts")) as JSONArray).objects()},
            current={inWorkspace(id,stamp)&&request==refreshSequence},
            denied={it is ApiFailure&&it.status in setOf(403,404)},
            invalidate={readEpoch++;records=emptyList();banks=emptyList();recordsReady=false;detail=null;statement=null;closePdf();editor?.preview=null},
            publish={rows,accounts->records=rows;banks=accounts;recordsReady=true;revision++})
    }
    fun navigate(key:String){page=key;error="";notice=""}
    fun endLocalSession(){sessionGeneration++;apiVersion="unknown";apiBuildRevision="unknown";capabilityLimits=emptyMap();capabilityChecking=false;capabilityRetryable=false;supportedFeatures=emptySet();capabilitiesLoaded=false;capabilitiesRequest?.cancel();capabilitiesRequest=null;api.forget();signedIn=false;company=JSONObject();companies=emptyList();records=emptyList();banks=emptyList();recordsReady=false;editor=null;detail=null;statement=null;pdf=null;tool="";toolData=null;posDrafts.clear();recurringCommands.clear();toolDrafts.clear();attachmentDrafts.clear();backupDrafts.values.forEach{runCatching{it.localCleanup()}};backupDrafts.clear();companyForm=false;page="dashboard";error="";notice="";generation++;companyLoads++;refreshSequence++}
    suspend fun logout(){check(backupDrafts.values.none{it.pending.isNotBlank()} && attachmentDrafts.values.none{it.unresolved} && !toolDrafts.hasUnresolved && posDrafts.values.none{it.submission.unresolved} && recurringCommands.values.none{it.unresolved} && editor?.retryPending != true){"A save may already have posted. Return to the pending entry, recurring schedule, or held Point of Sale cart and retry the original save before signing out."};try{api.logout()}finally{endLocalSession()}}
    fun add(kind:String){if(!recordsReady){error="Wait for the complete company history before starting an entry.";return};editor=EntryEditor(this,kind)}
    fun edit(row:JSONObject){if(!canWrite)return;val id=companyId;val stamp=generation;val access=readStamp();task{try{val full=api.record(id,row.s("id"));val source=if(full.s("kind")=="debit_note"&&full.o("data").s("applied_to").isNotBlank())api.record(id,full.o("data").s("applied_to"))else null;if(stamp==generation&&canRead(id,access)&&canWrite)editor=EntryEditor(this,full.s("kind"),previous=full).also{if(source!=null)it.setReturnSourceLines(source)}}catch(e:Exception){if(e is kotlinx.coroutines.CancellationException)throw e;if(stamp==generation&&canRead(id,access))throw e}}}
    fun convert(row:JSONObject,targetKind:String?=null){if(!canWrite)return;val id=companyId;val stamp=generation;val access=readStamp();task{try{val full=api.record(id,row.s("id"));if(stamp==generation&&canRead(id,access)&&canWrite)editor=EntryEditor(this,targetKind?:if(full.s("kind")=="purchase_order")"purchase_bill" else "sales_invoice",conversion=full)}catch(e:Exception){if(e is kotlinx.coroutines.CancellationException)throw e;if(stamp==generation&&canRead(id,access))throw e}}}
    fun closePdf(){pdfRequest++;pdfLoading=false;pdfError="";pdf=null}
    fun documentPdf(row:JSONObject,template:String=""){
        val id=companyId;val stamp=generation;val previous=pdf;val requestedPage=page;val request=++pdfRequest;val access=readStamp()
        val snapshot=JSONObject(row.toString())
        pdfLoading=true;pdfError="";pdfRequestedTemplate=template
        fun current()=request==pdfRequest&&inWorkspace(id,stamp)&&canRead(id,access)&&pdf===previous&&page==requestedPage
        task{
            try{
                val bytes=api.bytes(api.company(id,"/documents/${encode(snapshot.s("id"))}.pdf")+if(template.isBlank())"" else "?template=${encode(template)}")
                if(current())pdf=PdfView(bytes,"${friendly(snapshot.s("kind"))} ${snapshot.s("number")}.pdf",snapshot,template)
            }catch(e:Exception){
                if(e is kotlinx.coroutines.CancellationException)throw e
                if(current()){pdfError=e.message?:"Could not load this format. The previous PDF is unchanged.";if(previous==null||e is ApiFailure&&e.status==401)failure(e)}
            }finally{if(request==pdfRequest)pdfLoading=false}
        }
    }
    fun key()=UUID.randomUUID().toString()
}

private val acronymLabels=setOf("GST","GSTIN","CGST","SGST","IGST","HSN","SAC","IFSC","UPI","MRP","POS","PDF","XLSX","ITC","GSTR1","GSTR2A","GSTR3B","B2B","B2C","B2CS","B2CL","ID")
fun friendly(text:String)=text.replace('_',' ').split(' ').joinToString(" "){word->val upper=word.uppercase(java.util.Locale.ROOT);if(upper in acronymLabels)upper else word.replaceFirstChar{c->c.uppercase()}}
