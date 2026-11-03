package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import org.json.JSONArray
import org.json.JSONObject

@Composable fun JournalTool(vm:AppModel,reversing:Boolean=false){
    val cid=vm.companyId
    val originalId=remember(cid,reversing){if(reversing)vm.toolData?.s("id").orEmpty() else ""}
    val scope=if(reversing)"reverse_journal:$originalId"else"journal:create"
    val stamp=remember(cid,scope){vm.workspaceStamp()}
    val draft=remember(cid,scope){vm.toolDraft(scope)}
    val values=remember(draft){draft.values.apply{
        if(!containsKey("date"))put("date",today())
        if(!containsKey("lines"))put("lines",JSONArray(listOf(JSONObject().put("account_id","").put("debit","0").put("credit","0"),JSONObject().put("account_id","").put("debit","0").put("credit","0"))).toString())
    }}
    var accounts by remember{mutableStateOf(vm.toolData?.a("accounts")?.objects()?:emptyList())}
    var pending by remember(draft){mutableStateOf(draft.submission.unresolved)}
    var sending by remember{mutableStateOf(false)}
    fun current()=vm.inWorkspace(cid,stamp)&&vm.canWrite
    fun rows()=JSONArray(values["lines"]).objects()
    fun close(){check(vm.inWorkspace(cid,stamp)){"The original journal workspace changed."};vm.finishToolDraft(scope);vm.tool="";vm.toolData=null;vm.error=""}
    fun value(key:String)=values[key].orEmpty()
    fun updateLine(index:Int,key:String,value:String){val list=rows().toMutableList();list[index]=copy(list[index]).put(key,value);values["lines"]=JSONArray(list).toString()}
    LaunchedEffect(cid,scope){if(!reversing&&accounts.isEmpty())try{val loaded=(vm.api.request(vm.api.company(cid,"/accounts"))as JSONArray).objects();if(current())accounts=loaded}catch(error:Exception){vm.failure(error)}}
    ActionDialog(if(reversing)"Reverse journal"else"Balanced journal entry",vm,
        enabled=vm.supports("journal_idempotency")&&vm.canWrite&&!draft.journalReviewRequired,
        confirm=if(pending)"Retry original save"else if(reversing)"Post reversal"else"Post journal",
        unresolved={draft.submission.unresolved},working={sending},onDismiss=::close,onSave={
            check(!reversing||originalId.isNotBlank()){ "The original journal is missing. Close and reload it." }
            val body=JSONObject().put("date",value("date")).put("reference",value("reference"))
            if(reversing)body.put("reason",value("reason"))else body.put("memo",value("memo")).put("lines",JSONArray(value("lines")))
            sending=true
            try{
                submitJournal(draft,body,vm.supports("journal_idempotency"),::current,originalJournalId=originalId.takeIf{reversing}){frozen,key->
                    pending=true
                    vm.api.request(vm.api.company(cid,if(reversing)"/journals/${encode(originalId)}/reverse"else"/journals"),"POST",frozen,key) as JSONObject
                }
                pending=false;close();vm.refresh()
            }finally{pending=draft.submission.unresolved;sending=false}
        }){
        if(!vm.supports("journal_idempotency"))FeatureUpgradeHint(vm)
        if(draft.journalReviewRequired)Message("This command requires reconciliation. Copy any needed entries, close and review journal history before reopening a new journal command. No replacement was posted.")
        if(sending||pending){
            Message(if(sending)"Posting the original journal request…"else"The outcome is unknown. Retry original save uses the same journal, date, reference, lines and key. Resolve it before closing or creating a replacement.")
            Text("Date ${value("date")} · Reference ${value("reference")}")
        }else{
            if(reversing)Text("The original entry stays in audit history. This posts an equal opposite journal.")
            DateField(if(reversing)"Reversal date"else"Date",value("date"),{values["date"]=it})
            Field(if(reversing)"Reversal reference"else"Unique reference",value("reference"),{values["reference"]=it},maximum=80)
            Field(if(reversing)"Reason"else"Memo",value(if(reversing)"reason"else"memo"),{values[if(reversing)"reason"else"memo"]=it},maximum=500)
            if(!reversing){
                val lines=rows()
                lines.forEachIndexed{index,row->Section("Line ${index+1}"){
                    Choice("Account",row.s("account_id"),listOf("" to "Choose account")+accounts.map{it.s("id") to "${it.s("code")} · ${it.s("name")}"},{updateLine(index,"account_id",it)})
                    Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){
                        Field("Debit (₹)",row.s("debit"),{updateLine(index,"debit",it)},Modifier.weight(1f),number=true)
                        Field("Credit (₹)",row.s("credit"),{updateLine(index,"credit",it)},Modifier.weight(1f),number=true)
                    }
                    if(lines.size>2)TextButton(onClick={values["lines"]=JSONArray(lines.filterIndexed{i,_->i!=index}).toString()}){Text("Remove line")}
                }}
                OutlinedButton(enabled=lines.size<100,onClick={values["lines"]=JSONArray(lines+JSONObject().put("account_id","").put("debit","0").put("credit","0")).toString()}){Text("Add line")}
                val debit=lines.fold(java.math.BigDecimal.ZERO){sum,row->sum+row.decimal("debit")};val credit=lines.fold(java.math.BigDecimal.ZERO){sum,row->sum+row.decimal("credit")}
                Text("Debit ${money(debit)} · Credit ${money(credit)} · Difference ${money(debit-credit)}")
            }
        }
    }
}
