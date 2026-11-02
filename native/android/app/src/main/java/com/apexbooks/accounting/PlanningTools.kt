package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import java.math.BigDecimal

fun masterPlanningIssue(kind:String,days:String,threshold:String,creditLimit:String=""):String? {
    if(kind=="party"&&creditLimit.isNotBlank()){val number=creditLimit.toBigDecimalOrNull();if(number==null||number<BigDecimal.ZERO||number>BigDecimal("9999999999999.99")||number.stripTrailingZeros().scale()>2)return "Credit limit must be nonnegative, at most 9999999999999.99, with at most 2 decimal places, or blank."}
    if(kind=="party"&&days.isNotBlank()&&(days.toIntOrNull() !in 0..3650))return "Payment terms must be a whole number from 0 to 3650 days, or blank."
    if(kind=="item"&&threshold.isNotBlank()) {
        val number=threshold.toBigDecimalOrNull()
        if(number==null||number<BigDecimal.ZERO||number>BigDecimal("999999999999.999")||number.scale()>3)return "Low-stock threshold must be nonnegative, with at most 3 decimal places, or blank."
    }
    return null
}

@Composable fun PartyTermsSuggestion(editor:EntryEditor) {
    val party=editor.get("party_id");val date=editor.get("date");val vm=editor.vm
    if(party.isBlank())return
    var suggestion by remember(party,date){mutableStateOf<JSONObject?>(null)}
    TextButton(enabled=!editor.saving&&!editor.retryPending&&vm.busy==0,onClick={vm.task{
        val result=vm.api.request(vm.api.company(editor.companyId,"/parties/${encode(party)}/due-date?document_date=${encode(date)}"))as JSONObject
        if(vm.editor===editor&&editor.get("party_id")==party&&editor.get("date")==date)suggestion=result
    }}){Text("Check party payment terms")}
    suggestion?.let{result->val due=result.s("suggested_due_date")
        if(due.isBlank())Text("No default payment terms are set for this party.",style=MaterialTheme.typography.bodySmall)
        else {Text("${result.s("payment_terms_days")} days · suggested due date $due",style=MaterialTheme.typography.bodySmall)
            OutlinedButton(enabled=!editor.retryPending&&!editor.saving,onClick={editor.set("due_date",due);suggestion=null}){Text(if(editor.get("due_date").isBlank())"Use suggested due date"else"Replace due date with $due")}}
    }
}

@Composable fun ItemPriceSuggestion(editor:EntryEditor,line:LineState) {
    val party=editor.get("party_id");val item=line.get("item_id");val vm=editor.vm
    if(party.isBlank()||item.isBlank())return
    var result by remember(party,item){mutableStateOf<JSONObject?>(null)}
    val side=if(editor.purchase)"purchase"else"sales"
    TextButton(enabled=!editor.saving&&!editor.retryPending&&vm.busy==0,onClick={vm.task{
        val response=vm.api.request(vm.api.company(editor.companyId,"/parties/${encode(party)}/item-prices?item_id=${encode(item)}&side=$side"))as JSONObject
        if(vm.editor===editor&&editor.lines.contains(line)&&editor.get("party_id")==party&&line.get("item_id")==item)result=response
    }}){Text("Check this party’s item prices")}
    result?.let{price->Section("Price suggestion · review before applying"){
        Text(if(price.s("source")=="last_posted")"Last posted price for this exact party and item."else"No posted party history; showing the item’s default price.",style=MaterialTheme.typography.bodySmall)
        val inclusive=price.optBoolean("suggested_price_includes_tax")
        Text("${money(price.s("suggested_rate"))} · ${if(inclusive)"includes GST"else"excludes GST"}")
        for(row in price.a("history").objects())Text("${row.s("date")} · ${row.s("number")} · qty ${row.s("quantity")} · ${money(row.s("rate"))} (${if(row.optBoolean("price_includes_tax"))"incl."else"excl."} GST ${row.s("gst_rate") }%)",style=MaterialTheme.typography.bodySmall)
        Text("Applying changes only rate and inclusive/exclusive tax basis. Review this line’s GST and discounts; other values are kept.",style=MaterialTheme.typography.bodySmall)
        OutlinedButton(enabled=!editor.retryPending&&!editor.saving,onClick={line.set("rate",price.s("suggested_rate"));line.set("price_includes_tax",inclusive.toString());result=null}){Text("Apply suggested price & tax basis")}
    }}
}

@Composable fun ReorderTool(vm:AppModel) {
    val cid=vm.companyId;val stamp=vm.workspaceStamp()
    val quantities=remember{mutableStateMapOf<String,String>()};var search by remember{mutableStateOf("")};var date by remember{mutableStateOf(today())};var apply by remember{mutableIntStateOf(0)}
    var report by remember{mutableStateOf<JSONObject?>(null)};var failure by remember{mutableStateOf("")};var loadedDate by remember{mutableStateOf("")}
    LaunchedEffect(cid,apply){report=null;failure="";val requested=date
        try{val response=vm.api.request(vm.api.company(cid,"/reports/reorder?as_of=${encode(requested)}"))as JSONObject
            if(vm.inWorkspace(cid,stamp)){report=response;loadedDate=requested;quantities.clear()}
        }catch(e:Exception){currentCoroutineContext().ensureActive();failure=e.message?:"Could not load reorder review.";if(e is ApiFailure&&e.status==401)vm.failure(e)}
    }
    val rows=report?.a("rows")?.objects().orEmpty();val shown=rows.filter{it.s("name").contains(search.trim(),true)}.take(100);fun quantity(row:JSONObject)=quantities[row.s("item_id")]?:row.s("suggested_quantity")
    val invalidQuantity=shown.any{masterPlanningIssue("item","",quantity(it))!=null}
    val orderable=shown.filter{(quantity(it).toBigDecimalOrNull()?:BigDecimal.ZERO)>BigDecimal.ZERO}
    ActionDialog("Low stock & reorder review",vm,confirm="Done",onDismiss={vm.tool=""},onSave={vm.tool=""}){
        Text("Stock as of the selected date. Review a purchase-order draft before ordering; this report never creates purchases or moves stock.")
        DateField("As of",date,{date=it});OutlinedButton(onClick={apply++},enabled=vm.busy==0){Text("Refresh stock")}
        if(failure.isNotBlank())Message(failure,true)
        if(report==null&&failure.isBlank())LinearProgressIndicator(Modifier.fillMaxWidth())
        if(report!=null){Text("${report!!.s("total_low_stock")} items at or below threshold · as of $loadedDate")
            if(loadedDate!=date)Text("Refresh stock to use the changed date.",color=MaterialTheme.colorScheme.error)
            if(rows.isEmpty())Text("No low-stock items. Set an optional low-stock threshold on tracked goods to enable alerts.")
            Field("Find item",search,{search=it});Text("Showing up to 100 matching items. The draft uses these visible items with positive suggested quantities.",style=MaterialTheme.typography.bodySmall)
            for(row in shown)Section(row.s("name")){
                DetailValue("On hand",row.s("on_hand")+" "+row.s("unit"));DetailValue("Threshold",row.s("low_stock_threshold"));DetailValue("Suggested to buy",row.s("suggested_quantity"));Text("Valuation: ${friendly(row.s("valuation_status"))}",style=MaterialTheme.typography.bodySmall);if(vm.canWrite)Field("Order quantity · 0 excludes item",quantity(row),{quantities[row.s("item_id")]=it},number=true,maximum=18)
            }
            if(invalidQuantity)Text("Use nonnegative quantities with at most 3 decimal places.",color=MaterialTheme.colorScheme.error)
            if(vm.canWrite)Button(enabled=!invalidQuantity&&orderable.isNotEmpty()&&loadedDate==date&&vm.recordsReady,onClick={
                if(!vm.inWorkspace(cid,stamp))return@Button
                val masters=vm.records.filter{it.s("kind")=="item"}.associateBy{it.s("id")}
                if(orderable.any{!masters.containsKey(it.s("item_id"))}){vm.error="Some item details are not loaded. Close this review, refresh company data, then retry; tax details must be complete.";return@Button}
                val draft=EntryEditor(vm,"purchase_order");draft.lines.clear()
                for(row in orderable){val item=masters.getValue(row.s("item_id"));val line=LineState(JSONObject().put("itc_treatment",item.o("data").s("itc_treatment").ifBlank{"pending_review"}),regular=vm.regular);line.linkProduct(item,true,vm.regular);line.set("quantity",quantity(row));line.set("rate",row.s("purchase_rate"));draft.lines.add(line)}
                vm.tool="";vm.editor=draft;vm.notice="Review supplier, quantities and prices. This order is not saved yet; saving it will not change stock."
            }){Text("Review purchase order · ${orderable.size} items")}
            else Text("Read-only access · ask an owner or editor to prepare an order.")
        }
        Spacer(Modifier.height(8.dp))
    }
}
