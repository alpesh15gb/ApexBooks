package com.apexbooks.accounting

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal

fun bankMovement(row:JSONObject,bank:String):BigDecimal {
    val data=row.o("data");val kind=row.s("kind");val source=data.s("bank_account_id").ifBlank{"default"};val amount=row.decimal("amount")
    if(kind=="bank_transfer"){if(data.s("direction")=="bank_to_bank")return if(data.s("to_bank_account_id")==bank)amount else if(source==bank)-amount else BigDecimal.ZERO;if(source!=bank)return BigDecimal.ZERO;return if(data.s("direction")=="cash_to_bank")amount else -amount}
    if(data.s("payment_account")!="bank"||source!=bank)return BigDecimal.ZERO
    return when{kind in setOf("payment_in","pos","supplier_refund")||kind=="advance_refund"&&data.s("payment_kind")=="payment_out"->amount;kind in setOf("payment_out","expense","customer_refund","advance_refund")->-amount;else->BigDecimal.ZERO}
}
@Composable fun BankScreen(vm:AppModel){var bank by remember{mutableStateOf("default")};var asOf by remember{mutableStateOf(today())};var opening by remember{mutableStateOf("0")};var revision by remember{mutableIntStateOf(0)};var lines by remember{mutableStateOf(emptyList<JSONObject>())};var allLines by remember{mutableStateOf(emptyList<JSONObject>())};var report by remember{mutableStateOf<JSONObject?>(null)};var reviews by remember{mutableStateOf<Any?>(null)};var matching by remember{mutableStateOf<JSONObject?>(null)};var matchId by remember{mutableStateOf("")};var matchAmount by remember{mutableStateOf("")};var reviewNote by remember{mutableStateOf("")}
    var lineContext by remember{mutableStateOf<Pair<String,Int>?>(null)}
    LaunchedEffect(vm.companyId,bank,revision,vm.revision){report=null;lineContext=null;try{val cid=vm.companyId;val stamp=vm.workspaceStamp();val root=vm.api.company(cid);val query="?bank_account_id=${encode(bank)}&as_of=$asOf";coroutineScope{val a=async{(vm.api.request(root+"/bank-statement"+query)as JSONArray).objects()};val b=async{(vm.api.request(root+"/bank-statement?bank_account_id=${encode(bank)}")as JSONArray).objects()};val c=async{vm.api.request(root+"/bank-reconciliation"+query+"&opening_balance=${encode(opening)}")as JSONObject};val d=async{vm.api.request(root+"/bank-reconciliation/reviews?bank_account_id=${encode(bank)}")};lines=a.await();allLines=b.await();report=c.await();reviews=d.await();if(vm.inWorkspace(cid,stamp))lineContext=cid to stamp}}catch(e:Exception){currentCoroutineContext().ensureActive();vm.failure(e)}}
    val shownContext=lineContext
    fun unmatch(line:JSONObject){
        if(!vm.supports("bank_match_revisions")){vm.error="Protected bank unmatching is unavailable. ${vm.capabilityHint}";return}
        val context=shownContext?:run{vm.error="Wait for the statement to finish loading before unmatching.";return}
        val selectedBank=bank;val selectedDate=asOf
        val intent=try{BankUnmatchIntent(context.first,context.second,line)}catch(error:Exception){vm.failure(error);return}
        vm.task{
            intent.execute(vm.supports("bank_match_revisions"),{vm.inWorkspace(intent.companyId,intent.workspaceStamp)&&vm.canWrite&&bank==selectedBank&&asOf==selectedDate}){company,id,body->
                vm.api.request(vm.api.company(company,"/bank-statement/${encode(id)}/match"),"DELETE",body)
            }
            revision++
        }
    }
    val used=allLines.flatMap{it.a("allocations").objects()}.groupBy{it.s("record_id")}.mapValues{(_,rows)->rows.fold(BigDecimal.ZERO){sum,row->sum+row.decimal("amount")}}
    fun candidates(line:JSONObject)=vm.records.filter{it.optBoolean("posted")&&it.s("date")<=asOf&&bankMovement(it,bank).signum()==line.decimal("amount").signum()&&bankMovement(it,bank).signum()!=0&&it.decimal("amount")-(used[it.s("id")]?:BigDecimal.ZERO)>BigDecimal.ZERO&&allLines.none{l->l.s("matched_record_id")==it.s("id")}}
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(14.dp)){item{Section("Reconcile a bank account"){Choice("Bank account",bank,vm.banks.map{it.s("id") to it.s("name")},{bank=it});DateField("As of",asOf,{asOf=it});Field("Statement opening balance (₹)",opening,{opening=it},number=true);Button(onClick={revision++},modifier=Modifier.fillMaxWidth()){Text("Reconcile")};if(vm.canWrite){Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){OutlinedButton(onClick={vm.tool="bank_new"}){Text("New bank")};OutlinedButton(onClick={vm.toolData=JSONObject().put("bank_account_id",bank);vm.tool="transfer"}){Text("Transfer")}};OutlinedButton(onClick={vm.toolData=JSONObject().put("bank_account_id",bank);vm.tool="statement_import"},modifier=Modifier.fillMaxWidth()){Text("Import bank statement CSV")}};OutlinedButton(onClick={vm.toolData=JSONObject().put("bank_account_id",bank);vm.tool="cashbook"}){Text("Cash and bank book")}}};report?.let{value->item{Column(verticalArrangement=Arrangement.spacedBy(14.dp)){ReportContent(value,"Reconciliation")}}};lines.forEach{line->item(key=line.s("id")){Section("${line.s("date")} · ${money(line.s("amount"))}"){Text(line.s("description"));Text(line.s("reference"),style=MaterialTheme.typography.bodySmall);line.a("allocations").objects().forEach{allocation->val row=vm.records.find{it.s("id")==allocation.s("record_id")};Text("${row?.s("number")} · ${row?.s("name")} · ${money(allocation.s("amount"))}");if(vm.canWrite)TextButton(onClick={vm.task{vm.api.request(vm.api.company(vm.companyId,"/bank-statement/allocations/${allocation.s("id")}"),"DELETE");revision++}}){Text("Remove match")}};if(vm.canWrite&&line.s("matched_record_id").isNotBlank())Column{TextButton(enabled=shownContext!=null&&vm.supports("bank_match_revisions")&&vm.busy==0,onClick={unmatch(line)}){Text("Unmatch")};if(!vm.supports("bank_match_revisions"))FeatureUpgradeHint(vm)};if(vm.canWrite&&line.decimal("remaining_amount")>BigDecimal.ZERO&&line.s("matched_record_id").isBlank())OutlinedButton(onClick={matching=line;matchId="";matchAmount=line.s("remaining_amount")}){Text("Match ${money(line.s("remaining_amount"))} remaining")}}}};if(vm.canWrite)item{Section("Save dated review"){Field("Review note",reviewNote,{reviewNote=it},multiline=true,maximum=500);Button(onClick={vm.task{vm.api.request(vm.api.company(vm.companyId,"/bank-reconciliation/reviews"),"POST",JSONObject().put("bank_account_id",bank).put("as_of",asOf).put("opening_balance",opening).put("note",reviewNote));reviewNote="";revision++}}){Text("Save review")}}};if(reviews!=null)item{ReportContent(reviews,"Review history")}}
    matching?.let{line->ActionDialog("Match bank statement",vm,confirm="Allocate match",onDismiss={matching=null},onSave={vm.api.request(vm.api.company(vm.companyId,"/bank-statement/${line.s("id")}/allocations"),"POST",JSONObject().put("record_id",matchId).put("amount",matchAmount));matching=null;revision++}){Text("${line.s("description")} · ${money(line.s("amount"))}");Choice("Posted transaction",matchId,listOf("" to "Choose transaction")+candidates(line).map{it.s("id") to "${it.s("number")} · ${it.s("name")} · ${money(it.decimal("amount")-(used[it.s("id")]?:BigDecimal.ZERO))} available"},{id->matchId=id;candidates(line).find{it.s("id")==id}?.let{val available=it.decimal("amount")-(used[id]?:BigDecimal.ZERO);matchAmount=line.decimal("remaining_amount").min(available).toPlainString()}});Field("Match amount (₹)",matchAmount,{matchAmount=it},number=true)}}
}

@Composable fun LedgerScreen(vm:AppModel){var accounts by remember{mutableStateOf<JSONArray?>(null)};var journals by remember{mutableStateOf<JSONArray?>(null)};var trial by remember{mutableStateOf<Any?>(null)}
    LaunchedEffect(vm.companyId,vm.revision){try{coroutineScope{val a=async{vm.api.request(vm.api.company(vm.companyId,"/accounts"))as JSONArray};val b=async{vm.api.request(vm.api.company(vm.companyId,"/journals"))as JSONArray};val c=async{vm.api.request(vm.api.company(vm.companyId,"/trial-balance"))};accounts=a.await();journals=b.await();trial=c.await()}}catch(e:Exception){currentCoroutineContext().ensureActive();vm.failure(e)}}
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(14.dp)){if(vm.canWrite)item{Section("Ledger entry"){Button(onClick={vm.toolData=JSONObject().put("accounts",accounts);vm.tool="journal"}){Text("New balanced journal")};OutlinedButton(onClick={vm.tool="ledger_account"}){Text("Add ledger account")}}};if(trial!=null)item{Column(verticalArrangement=Arrangement.spacedBy(14.dp)){ReportContent(trial,"Trial balance")}};if(accounts!=null)item{ReportContent(accounts,"Chart of accounts")};journals?.objects()?.forEach{journal->item(key=journal.s("id")){Section("${journal.s("date")} · ${journal.s("reference")}"){Text(journal.s("memo"));journal.a("lines").objects().forEach{line->val account=accounts?.objects()?.find{it.s("id")==line.s("account_id")};Text("${account?.s("name")} · Dr ${money(line.s("debit"))} · Cr ${money(line.s("credit"))}",style=MaterialTheme.typography.bodySmall)};if(vm.canWrite&&journal.s("source_record_id").isBlank()&&journal.s("reversed_by").isBlank()&&journal.s("reversal_of").isBlank())TextButton(onClick={vm.toolData=journal;vm.tool="reverse_journal"}){Text("Reverse journal")}}}}}
}
