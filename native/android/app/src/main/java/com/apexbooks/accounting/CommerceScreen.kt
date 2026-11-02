package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import com.apexbooks.accounting.data.*

@Composable fun CommerceScreen(vm:AppModel){
    val cid=vm.companyId;val root=vm.api.company(cid,"/commerce/connections")
    var connections by remember(cid){mutableStateOf(emptyList<JSONObject>())};var selected by remember(cid){mutableStateOf("")}
    var workspace by remember(cid){mutableStateOf(JSONObject())};var section by remember(cid){mutableStateOf("overview")}
    var connect by remember(cid){mutableStateOf(false)};var setup by remember(cid){mutableStateOf<JSONObject?>(null)}
    var mapping by remember(cid){mutableStateOf(false)};var openedOrder by remember(cid){mutableStateOf<JSONObject?>(null)}
    var moneyForm by remember(cid){mutableStateOf(false)}
    val clipboard=LocalClipboardManager.current
    suspend fun load(id:String=selected){if(id.isBlank())return;val data=vm.api.request("$root/$id/workspace") as JSONObject;if(vm.companyId==cid&&selected==id)workspace=data}
    val pendingCommands=remember(cid){java.util.concurrent.ConcurrentHashMap<String,String>()}
    fun command(operation:String,payload:JSONObject=JSONObject(),onQueued:(()->Unit)?=null){val id=selected;val intent="$id:$operation:$payload";val key=pendingCommands.getOrPut(intent){UUID.randomUUID().toString()};vm.task{vm.api.request("$root/$id/commands","POST",JSONObject().put("command_id",key).put("operation",operation).put("payload",payload));pendingCommands.remove(intent);if(vm.companyId==cid){vm.notice="Action queued. Delivery and accounting results appear in this workspace.";onQueued?.invoke();load(id)}}}
    LaunchedEffect(cid){try{val rows=(vm.api.request(root) as JSONArray).objects();connections=rows;selected=rows.firstOrNull()?.s("id")?:""}catch(e:Exception){vm.failure(e)}}
    LaunchedEffect(cid,selected){workspace=JSONObject();if(selected.isNotBlank())while(isActive){try{load()}catch(e:Exception){vm.failure(e)};delay(5000)}}
    val connection=workspace.optJSONObject("connection")?:JSONObject();val active=connection.s("status")=="active"
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(16.dp)){
        item{Heading("Ecommerce","Independent store channels and stock pools for ${vm.company.s("name")}")}
        item{Section{
            if(connections.isNotEmpty())Choice("Bagisto store channel",selected,connections.map{it.s("id") to "${it.s("name")} · ${it.s("channel")}"},{selected=it})
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){if(vm.isOwner)Button(onClick={connect=true}){Text("Connect Bagisto")};OutlinedButton(enabled=selected.isNotBlank(),onClick={vm.task{load()}}){Text("Refresh")}}
            if(connection.length()>0){Text("${friendly(connection.s("status"))} · INR · ${connection.s("channel")}",style=MaterialTheme.typography.titleSmall);Text(connection.s("base_url"),style=MaterialTheme.typography.bodySmall)
                if(vm.isOwner)Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){OutlinedButton(onClick={vm.task{vm.api.request("$root/$selected/verify","POST");load()}}){Text("Verify bridge")};OutlinedButton(onClick={vm.task{vm.api.request("$root/$selected/state","PUT",JSONObject().put("status",if(active)"paused"else"active"));load()}}){Text(if(active)"Pause"else"Activate")}}
            }
        }}
        if(selected.isBlank())item{Section{Text("Connect a Bagisto channel to import its orders, payments and stock into this company.")}}
        else{
            item{Section{Choice("Workspace",section,listOf("overview" to "Overview","catalogue" to "Catalogue & mappings","orders" to "Store orders","payments" to "Payments, payouts & returns","deliveries" to "Delivery queues","reconciliation" to "Reconciliation"),{section=it})}}
            when(section){
                "overview"->item{Section("Store overview"){
                    Text("${workspace.optJSONArray("orders")?.length()?:0} orders · ${workspace.optJSONArray("stock")?.length()?:0} mapped SKUs",style=MaterialTheme.typography.titleLarge)
                    Text("Checkout reserves stock before accepting an order. Invoices post sales, GST and cost. Captures enter clearing; settlements move bank net and fees. Exceptions remain in review.")
                    if(vm.canWrite){OutlinedButton(enabled=active,onClick={command("history.scan",JSONObject().put("after_id",0))}){Text("Repair / scan store history")};Button(enabled=active,onClick={command("reconcile.snapshot")}){Text("Reconcile store")}}
                }}
                "catalogue"->{
                    item{Section("Product & customer mappings"){Text("Select the exact store identity, SKU and accounting record in this company.");if(vm.canWrite){Button(onClick={mapping=true}){Text("Add / review mapping")};OutlinedButton(enabled=active,onClick={command("catalogue.scan")}){Text("Read store catalogue")};OutlinedButton(enabled=active,onClick={command("catalogue.publish")}){Text("Publish accounting prices & stock")}}}}
                    items(workspace.optJSONArray("stock")?.objects()?:emptyList(),key={it.s("external_id")}){row->Section(row.s("name")){Text(row.s("sku"),style=MaterialTheme.typography.bodySmall);Text("Book ${row.s("book_quantity")} · Reserved ${row.s("reserved_quantity")}");Text("Sellable ${row.s("available_quantity")} · ${money(row.s("sale_rate"))}",color=MaterialTheme.colorScheme.primary)}}
                    val scan=workspace.optJSONArray("outbox")?.objects()?.firstOrNull{it.s("operation")=="catalogue.scan"&&it.s("status")=="done"}?.optJSONObject("result")?.optJSONArray("products")?.objects()?:emptyList()
                    if(scan.isNotEmpty())item{Section("Store catalogue"){scan.forEach{Text("${it.s("external_id")} · ${it.s("sku")} · ${it.s("name")}",style=MaterialTheme.typography.bodySmall)}}}
                }
                "orders"->{val orders=workspace.optJSONArray("orders")?.objects()?:emptyList();if(orders.isEmpty())item{Section{Text("Accepted store orders appear here after delivery.")}};items(orders,key={it.s("id")}){order->Section(order.s("number")){Text(money(order.s("amount")),style=MaterialTheme.typography.headlineSmall);Text(friendly(order.s("status")));OutlinedButton(onClick={openedOrder=order}){Text("Open order")}}}}
                "payments"->item{Section("Payments, payouts & returns"){Text("Record confirmed captures, advances, refunds, provider settlements and goods receipts using their source references.");if(vm.canWrite)Button(enabled=active,onClick={moneyForm=true}){Text("Record a source transaction")}}}
                "deliveries"->{for(direction in listOf("inbox","outbox")){
                    item{Heading(if(direction=="inbox")"Store → Books"else"Books → Store","Delivery exceptions stay visible until resolved.")}
                    items(workspace.optJSONArray(direction)?.objects()?:emptyList(),key={"$direction:${it.s("id")}"}){row->Section{
                        Text(friendly(row.s(if(direction=="inbox")"event_type"else"operation")),style=MaterialTheme.typography.titleSmall);Text("${friendly(row.s("status"))} · ${row.s("attempts")} attempts")
                        Text(row.s(if(direction=="inbox")"entity_id"else"command_id"),style=MaterialTheme.typography.bodySmall)
                        if(row.s("error").isNotBlank())Text(row.s("error"),color=MaterialTheme.colorScheme.error)
                        if(vm.canWrite&&row.s("status") in listOf("review","retry"))OutlinedButton(onClick={vm.task{vm.api.request("$root/$selected/retry/$direction/${row.s("id")}","POST");load()}}){Text("Retry delivery")}
                        val result=row.optJSONObject("result");if(row.s("event_type")=="invoice.created"&&result?.s("record_id")?.isNotBlank()==true)OutlinedButton(onClick={vm.documentPdf(JSONObject().put("id",result.s("record_id")).put("kind","sales_invoice").put("number",result.s("invoice_number")))}){Text("Invoice PDF")}
                    }}
                }
                }
                else -> {
                    item { Section("Store reconciliation") {
                        Text("Compare source totals and mapped sellable stock. Results remain in this company’s audit trail.")
                        if(vm.canWrite) Button(enabled=active,onClick={command("reconcile.snapshot")}){Text("Reconcile now")}
                    } }
                    items(workspace.optJSONArray("reconciliations")?.objects()?:emptyList(),key={it.s("id")}) { row ->
                        Section(friendly(row.s("status"))) {
                            val report=row.optJSONObject("report")?:JSONObject()
                            val store=report.optJSONObject("store")?:JSONObject()
                            Text(row.s("created_at"),style=MaterialTheme.typography.bodySmall)
                            Text("${report.optJSONArray("stock_differences")?.length()?:0} stock differences")
                            Text("Store invoices ${money(store.s("invoice_total"))} · Credits ${money(store.s("credit_total"))}")
                            report.optJSONArray("stock_differences")?.objects()?.forEach {
                                Text("Product ${it.s("product_id")}: Books ${it.s("expected")}, store ${it.s("actual")}")
                            }
                        }
                    }
                }
            }
        }
    }
    if(moneyForm)CommerceMoneyDialog(vm,selected,workspace){moneyForm=false}
    if(connect){var name by remember{mutableStateOf("")};var url by remember{mutableStateOf("")};var channel by remember{mutableStateOf("default")};var bank by remember{mutableStateOf("default")}
        AlertDialog(onDismissRequest={connect=false},title={Text("Connect Bagisto")},text={Column(Modifier.verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)){Text("This channel belongs to ${vm.company.s("name")}. Other companies need separate channels and inventory sources.");Field("Store name",name,{name=it});Field("Store HTTPS origin",url,{url=it});Field("Channel code",channel,{channel=it});Choice("Gateway clearing account",bank,listOf("default" to "Default bank clearing")+vm.banks.map{it.s("id") to it.s("name")},{bank=it})}},confirmButton={Button(enabled=vm.busy==0,onClick={vm.task{val result=vm.api.request(root,"POST",JSONObject().put("name",name.trim()).put("base_url",url.trim()).put("channel",channel.trim()).put("gateway_bank_id",bank)) as JSONObject;val safe=JSONObject(result.toString());safe.remove("setup_secret");if(vm.companyId==cid){connections=connections+safe;selected=result.s("id");setup=result;connect=false}}}){Text("Create connection")}},dismissButton={TextButton(onClick={connect=false}){Text("Cancel")}})
    }
    setup?.let{result->AlertDialog(onDismissRequest={setup=null},title={Text("Save server setup")},text={Column(verticalArrangement=Arrangement.spacedBy(12.dp)){Text("Shown once. Save this in the Bagisto server configuration, then verify and activate the connection.");Field("Connection ID",result.s("id"),{},readOnly=true);Field("Connection secret",result.s("setup_secret"),{},password=true,readOnly=true);OutlinedButton(onClick={clipboard.setText(AnnotatedString(JSONObject().put("connection_id",result.s("id")).put("secret",result.s("setup_secret")).put("channel",result.s("channel")).toString()))}){Text("Copy server setup")}}},confirmButton={TextButton(onClick={setup=null}){Text("I have saved this")}})}
    if(mapping){var type by remember{mutableStateOf("product")};var source by remember{mutableStateOf("")};var sku by remember{mutableStateOf("")};var target by remember{mutableStateOf("")};val candidates=vm.records.filter{it.s("kind")==if(type=="product")"item"else"party"}
        AlertDialog(onDismissRequest={mapping=false},title={Text("Store mapping")},text={Column(Modifier.verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)){Choice("Mapping type",type,listOf("product" to "Product → Item","customer" to "Customer → Party"),{type=it;target=""});Field("Store identity",source,{source=it});if(type=="product")Field("Exact store SKU",sku,{sku=it});Choice("Accounting record",target,candidates.map{it.s("id") to it.s("name")},{target=it})}},confirmButton={Button(enabled=vm.busy==0,onClick={val id=selected;vm.task{vm.api.request("$root/$id/links","POST",JSONObject().put("entity_type",type).put("external_id",source.trim()).put("record_id",target).put("sku",if(type=="product")sku.trim()else""));mapping=false;load(id)}}){Text("Save mapping")}},dismissButton={TextButton(onClick={mapping=false}){Text("Cancel")}})
    }
    openedOrder?.let{order->var operation by remember(order){mutableStateOf("order.invoice")};val quantities=remember(order){mutableStateMapOf<String,String>()};var carrier by remember(order){mutableStateOf("")};var tracking by remember(order){mutableStateOf("")}
        AlertDialog(onDismissRequest={openedOrder=null},title={Text("${order.s("number")} · ${money(order.s("amount"))}")},text={Column(Modifier.verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)){if(vm.error.isNotBlank())Text(vm.error,color=MaterialTheme.colorScheme.error);Text("Enter quantities for one action. Source stock and invoiced balances are checked before posting.");order.optJSONObject("snapshot")?.optJSONArray("items")?.objects()?.forEach{line->Field("${line.s("name")} · ordered ${line.s("quantity")}, invoiced ${line.s("invoiced")}, shipped ${line.s("shipped")}",quantities[line.s("id")]?:"",{quantities[line.s("id")]=it},number=true)};if(vm.canWrite){Choice("Action",operation,listOf("order.invoice" to "Create invoice","order.ship" to "Create shipment","order.refund" to "Create credit / refund","order.cancel" to "Cancel unfulfilled order"),{operation=it});if(operation=="order.ship"){Field("Carrier",carrier,{carrier=it});Field("Tracking number",tracking,{tracking=it})}}}},confirmButton={if(vm.canWrite)Button(enabled=active&&vm.busy==0,onClick={try{val items=JSONObject();quantities.forEach{(key,value)->if(value.isNotBlank()){val q=value.toIntOrNull()?:throw Exception("Enter whole-unit quantities.");if(q<0)throw Exception("Quantities cannot be negative.");if(q>0)items.put(key,q)}};if(operation!="order.cancel"&&items.length()==0)throw Exception("Enter at least one action quantity.");command(operation,JSONObject().put("order_id",order.s("external_id")).put("items",items).put("carrier",carrier).put("tracking",tracking)){openedOrder=null}}catch(e:Exception){vm.failure(e)}}){Text("Queue action")}},dismissButton={TextButton(onClick={openedOrder=null}){Text("Close")}})
    }
}
