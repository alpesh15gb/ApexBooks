package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

@Composable fun CommerceMoneyDialog(vm:AppModel,connectionId:String,workspace:JSONObject,onClose:()->Unit){
    val cid=vm.companyId;val key=remember(cid,connectionId){UUID.randomUUID().toString()}
    var kind by remember{mutableStateOf("capture")};var order by remember{mutableStateOf("")};var target by remember{mutableStateOf("")}
    var source by remember{mutableStateOf("")};var issued by remember{mutableStateOf(today())};var amount by remember{mutableStateOf("")}
    var net by remember{mutableStateOf("")};var fee by remember{mutableStateOf("0")};var bank by remember{mutableStateOf("")}
    var supply by remember{mutableStateOf("goods")};var gst by remember{mutableStateOf("0")};var pos by remember{mutableStateOf(workspace.optJSONObject("connection")?.optJSONObject("config")?.optJSONObject("capabilities")?.s("company_state_code")?:"")}
    val quantities=remember{mutableStateMapOf<String,String>()};val captureIds=remember{mutableStateListOf<String>()};val refundIds=remember{mutableStateListOf<String>()}
    val links=workspace.optJSONArray("links")?.objects()?:emptyList()
    fun docs(type:String)=links.filter{it.s("entity_type")==type&&it.optJSONObject("snapshot")?.s("order_id")==order}
    val credits=docs("credit");val invoices=docs("invoice");val captures=docs("capture")
    val note=credits.firstOrNull{it.s("external_id")==target}
    AlertDialog(onDismissRequest=onClose,title={Text("Payments, payouts & returns")},text={Column(Modifier.verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)){
        if(vm.error.isNotBlank())Text(vm.error,color=MaterialTheme.colorScheme.error)
        Text("Record confirmed source transactions. Invoice status alone is not evidence of payment.")
        Choice("Action",kind,listOf("capture" to "Payment received / captured","refund" to "Cash / gateway refund","settlement" to "Gateway settlement","receipt" to "Goods physically received"),{kind=it;target="";quantities.clear()})
        Field("Bank / provider / receipt reference",source,{source=it},maximum=160)
        Field("Accounting date · YYYY-MM-DD",issued,{issued=it})
        if(kind!="settlement")Choice("Store order",order,workspace.optJSONArray("orders")?.objects()?.map{it.s("external_id") to it.s("number")}?:emptyList(),{order=it;target="";quantities.clear()})
        if(kind=="capture")Choice("Invoice allocation",target,listOf("" to "Unapplied customer advance")+invoices.map{it.s("external_id") to "Invoice ${it.s("external_id")} · ${money(it.optJSONObject("snapshot")?.s("amount")?:"")}"},{target=it})
        if(kind=="refund")Choice("Original credit or advance",target,credits.map{"credit:${it.s("external_id")}" to "Credit ${it.s("external_id")}"}+captures.map{"capture:${it.s("external_id")}" to "Advance ${it.s("external_id")}"},{target=it})
        if(kind=="receipt"){
            Choice("Financial credit note",target,credits.map{it.s("external_id") to "Credit ${it.s("external_id")}"},{target=it;quantities.clear()})
            note?.optJSONObject("snapshot")?.optJSONArray("lines")?.objects()?.forEach{line->val id=line.s("product_id");val name=workspace.optJSONArray("stock")?.objects()?.firstOrNull{it.s("external_id")==id}?.s("name")?:id;Field("$name · received quantity · credited ${line.s("quantity")}",quantities[id]?:"",{quantities[id]=it},number=true)}
        }
        if(kind in listOf("capture","refund"))Field("Amount (₹)",amount,{amount=it},number=true)
        if(kind=="capture"&&target.isBlank()){
            Choice("Advance supply",supply,listOf("goods" to "Goods","services" to "Services"),{supply=it})
            if(supply=="services"){Choice("Advance GST rate",gst,listOf("0","5","12","18","28").map{it to "$it%"},{gst=it});Field("Advance place of supply · state code",pos,{pos=it},maximum=2)}
        }
        if(kind=="settlement"){
            for(type in listOf("capture","refund")){
                Text(if(type=="capture")"Captured receipts in payout"else"Refunds deducted by provider",style=MaterialTheme.typography.titleSmall)
                links.filter{it.s("entity_type")==type&&it.optJSONObject("snapshot")?.s("_settled").isNullOrBlank()}.forEach{row->val selected=if(type=="capture")captureIds else refundIds;val id=row.s("external_id");Row{Checkbox(id in selected,onCheckedChange={if(it)selected.add(id)else selected.remove(id)});Text("$id · ${money(row.optJSONObject("snapshot")?.s("amount")?:"")}")}}
            }
            Field("Bank net received (₹)",net,{net=it},number=true);Field("Provider fee excluding supplier GST (₹)",fee,{fee=it},number=true)
            Choice("Destination bank",bank,vm.banks.filter{it.s("id")!=workspace.optJSONObject("connection")?.optJSONObject("config")?.s("gateway_bank_id")}.map{it.s("id") to it.s("name")},{bank=it})
            Text("Captured gross minus selected refunds and fee must equal bank net. Record provider GST using its supplier bill.",style=MaterialTheme.typography.bodySmall)
        }
    }},confirmButton={Button(enabled=vm.busy==0,onClick={vm.task{
        if(source.isBlank())throw Exception("Enter the bank, provider or goods receipt reference.")
        val data=JSONObject().put("date",issued).put("order_id",order);val operation=when(kind){
            "capture"->{data.put("amount",amount);if(target.isNotBlank())data.put("allocations",JSONArray().put(JSONObject().put("invoice_id",target).put("amount",amount)))else data.put("advance_supply",supply).put("advance_gst_rate",gst).put("place_of_supply",pos);"payment.capture"}
            "refund"->{if(target.isBlank())throw Exception("Choose the original credit or advance.");data.put("amount",amount).put(if(target.startsWith("credit:"))"credit_id"else"capture_id",target.substringAfter(':'));"payment.refund"}
            "receipt"->{val lines=JSONArray();quantities.forEach{(id,value)->if((value.toBigDecimalOrNull()?:java.math.BigDecimal.ZERO)>java.math.BigDecimal.ZERO)lines.put(JSONObject().put("product_id",id).put("quantity",value))};if(lines.length()==0)throw Exception("Enter quantities physically received.");data.put("credit_id",target).put("lines",lines);"return.receive"}
            else->{data.remove("order_id");val gross=captureIds.fold(java.math.BigDecimal.ZERO){sum,id->sum+(links.first{it.s("entity_type")=="capture"&&it.s("external_id")==id}.optJSONObject("snapshot")!!.s("amount").toBigDecimal())};data.put("gross",gross.toPlainString()).put("net",net).put("fee",fee).put("capture_ids",JSONArray(captureIds)).put("refund_ids",JSONArray(refundIds)).put("bank_account_id",bank);"settlement.record"}
        }
        vm.api.request(vm.api.company(cid,"/commerce/connections/$connectionId/commands"),"POST",JSONObject().put("command_id",key).put("operation",operation).put("payload",JSONObject().put("source_id",source.trim()).put("confirmed",true).put("data",data)))
        if(vm.companyId==cid){vm.notice="Source transaction queued. Review its delivery result before recording it again.";onClose()}
    }}){Text("Confirm source & queue")}},dismissButton={TextButton(onClick=onClose){Text("Close")}})
}
