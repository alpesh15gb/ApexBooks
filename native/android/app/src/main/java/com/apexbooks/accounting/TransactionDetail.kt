@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject

@Composable fun TransactionDetail(vm: AppModel, initial: JSONObject) {
    val cid = vm.companyId
    var record by remember(initial.s("id")) { mutableStateOf<JSONObject?>(null) }
    var failure by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }
    LaunchedEffect(cid, initial.s("id"), vm.revision, reload) {
        record = null; failure = ""
        try { record = vm.api.record(cid, initial.s("id")) }
        catch (e: Exception) { currentCoroutineContext().ensureActive(); failure = e.message ?: "Could not load this transaction."; if (e is ApiFailure && e.status == 401) vm.failure(e) }
    }
    val row = record ?: initial
    val data = row.o("data")
    val editable = vm.canWrite && record != null && row.s("converted_to").isBlank() && row.s("kind") in (vm.documentKinds + setOf("payment_in", "payment_out", "item", "party"))
    val printable = record != null && row.s("kind") in (vm.documentKinds + setOf("payment_in", "payment_out", "customer_refund", "supplier_refund", "advance_refund"))
    Dialog(onDismissRequest = { vm.detail = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding(), color = MaterialTheme.colorScheme.background) {
            Scaffold(topBar = { TopAppBar(title = { Text(friendly(row.s("kind"))) }, navigationIcon = { IconButton(onClick = { vm.detail = null }) { Icon(Icons.Outlined.Close, "Close transaction") } }) }, bottomBar = {
                Surface(shadowElevation = 8.dp) { Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (printable) OutlinedButton(onClick = { vm.documentPdf(row) }, modifier = Modifier.weight(1f)) { Icon(Icons.Outlined.PictureAsPdf, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("PDF / share") }
                    if (editable) Button(onClick = { vm.detail = null; vm.edit(row) }, modifier = Modifier.weight(1f)) { Icon(Icons.Outlined.Edit, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Edit") }
                } }
            }) { padding -> LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                if (record == null && failure.isBlank()) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                if (failure.isNotBlank()) item { Message(failure, true); OutlinedButton(onClick={reload++}) { Text("Retry loading transaction") } }
                item { Section {
                    StatusPill(registerStatus(row))
                    Text(row.s("number").ifBlank { friendly(row.s("kind")) }, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text(row.s("name"), style = MaterialTheme.typography.bodyLarge)
                    Text(money(if(row.s("kind")=="item")data.s("sale_rate")else row.s("amount")), style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold, color = ApexGreen)
                    DetailValue("Date", row.s("date"))
                    if (data.s("due_date").isNotBlank()) { DetailValue("Due date", data.s("due_date")); if(row.decimal("outstanding").signum()>0&&data.s("due_date")<today())Text("Overdue · record a collection or review the party balance.",color=MaterialTheme.colorScheme.error,style=MaterialTheme.typography.bodySmall) }
                    if(row.s("kind")=="item"){DetailValue("Sale unit",data.s("unit"));DetailValue("HSN / SAC",data.s("hsn"))}
                    if (row.has("outstanding") && !row.isNull("outstanding")) DetailValue("Outstanding", money(row.s("outstanding")))
                    if (row.s("converted_to").isNotBlank()) Text(if(row.s("converted_to")=="source-converted")"Converted in the source system · the destination document was not included in this import."else"Converted · the source is retained for your audit trail", color = ApexGreen)
                    if(data.optBoolean("is_advance")) { DetailValue("Available advance",money(row.s("advance_remaining")));Text("An advance is money received or paid before allocation. It does not settle an invoice until applied.",style=MaterialTheme.typography.bodySmall) }
                    if(row.s("kind") in setOf("credit_note","debit_note")) DetailValue("Available note credit",money(row.s("credit_remaining")))
                    if(data.s("payment_account").isNotBlank()) DetailValue("Payment account",friendly(data.s("payment_account")))
                } }
                if (data.s("party_gstin").isNotBlank() || data.s("party_address").isNotBlank()) item { Section("Party details") {
                    if (data.s("party_gstin").isNotBlank()) DetailValue("GSTIN", data.s("party_gstin"))
                    if (data.s("party_address").isNotBlank()) Text(data.s("party_address"))
                    if (data.s("shipping_address").isNotBlank()) { Text("Ship to", style = MaterialTheme.typography.labelMedium); Text(data.s("shipping_address")) }
                } }
                if (vm.canWrite && record != null && row.decimal("outstanding").signum() > 0 && row.s("kind") in setOf("sales_invoice", "purchase_bill")) item {
                    FilledTonalButton(onClick = {
                        val kind = if (row.s("kind") == "sales_invoice") "payment_in" else "payment_out"
                        vm.detail = null; vm.add(kind)
                        vm.editor?.let { entry -> entry.chooseAllocation(entry.allocations.first(), 0, row.s("id")) }
                    }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Outlined.Payments, null); Spacer(Modifier.width(8.dp)); Text(if (row.s("kind") == "sales_invoice") "Record payment received" else "Record supplier payment") }
                }
                if(record!=null) item {
                    val links=listOf("Posted document" to row.s("converted_to"),"Source document" to data.s("source_document_id"),"Original invoice / bill" to data.s("applied_to")).filter{it.second.isNotBlank()&&it.second!="source-converted"}
                    if(links.isNotEmpty())Section("Related documents") { links.forEach{(label,id)->
                        val linked=vm.records.find{it.s("id")==id}
                        TextButton(onClick={vm.detail=linked?:JSONObject().put("id",id)}) { Text("$label · ${linked?.s("number")?.ifBlank{id.take(8)}?:id.take(8)} →") }
                    } }
                    val allocations=row.a("allocations").objects().ifEmpty{data.a("allocations").objects()}
                    if(allocations.isNotEmpty())Section("Payment allocation") { allocations.forEach{allocation->
                        val id=allocation.s("document_id");val target=vm.records.find{it.s("id")==id}
                        DetailValue(target?.s("number")?.ifBlank{"Invoice / bill"}?:"Invoice / bill",money(allocation.s("amount")))
                        if(id.isNotBlank())TextButton(onClick={vm.detail=target?:JSONObject().put("id",id)}){Text("Open allocated document →")}
                    };Text("Allocation settles the document. Bank matching is a separate reconciliation step.",style=MaterialTheme.typography.bodySmall) }
                    if(vm.canWrite&&row.optBoolean("posted")&&row.s("kind") in setOf("sales_invoice","pos","purchase_bill"))OutlinedButton(onClick={
                        val kind=if(row.s("kind")=="purchase_bill")"debit_note"else"credit_note"
                        vm.detail=null;vm.add(kind);vm.editor?.chooseSource(row.s("id"))
                    },modifier=Modifier.fillMaxWidth()){Text(if(row.s("kind")=="purchase_bill")"Create purchase return / debit note"else"Create sales return / credit note")}
                    val credit=row.decimal("credit_remaining").signum()>0
                    if(vm.canWrite&&(credit||row.decimal("advance_remaining").signum()>0))FilledTonalButton(onClick={
                        vm.detail=null;vm.toolData=JSONObject().put("source",row.s("id"));vm.tool=if(credit)"settle_credit"else"settle_advance"
                    },modifier=Modifier.fillMaxWidth()){Text(if(credit)"Apply / refund available credit"else"Apply / refund available advance")}
                    if(!vm.canWrite)Text("Read-only access · ask a company owner for editor access to record payments, returns or changes.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
                itemsIndexed(data.a("lines").objects()) { index, line -> Section {
                    Text("${index + 1}. ${line.s("description")}", fontWeight = FontWeight.SemiBold)
                    DetailValue("${line.s("quantity")} ${line.s("unit")} × ${money(line.s("rate"))}", money(line.decimal("taxable") + line.decimal("tax")))
                    if(line.has("discount_amount")&&!line.isNull("discount_amount"))DetailValue("Fixed line discount",money(line.s("discount_amount")))else if(line.decimal("discount_percent").signum()!=0)DetailValue("Line discount",line.s("discount_percent")+"%")
                    if(line.decimal("document_discount").signum()!=0)DetailValue("Document discount allocation",money(line.s("document_discount")))
                    if (vm.regular || line.decimal("tax").signum() != 0) DetailValue("GST ${line.s("gst_rate")}%", money(line.s("tax")))
                } }
                if(row.s("kind") in setOf("purchase_bill","expense")&&record!=null)item{OutlinedButton(onClick={vm.detail=null;vm.toolData=row;vm.tool="attachments"},modifier=Modifier.fillMaxWidth()){Text("Retained receipts & attachments")}}
                if (data.s("notes").isNotBlank()) item { Section("Notes") { Text(data.s("notes")) } }
                if (data.s("terms").isNotBlank()) item { Section("Terms") { Text(data.s("terms")) } }
                if (vm.canWrite && row.s("kind") in vm.draftKinds && row.s("converted_to").isBlank() && record != null) item {
                    OutlinedButton(onClick={vm.detail=null;vm.toolData=row;vm.tool="recurring_new"},modifier=Modifier.fillMaxWidth()){Text("Create recurring draft schedule")}
                    if(row.s("kind") in setOf("estimate","proforma"))OutlinedButton(onClick={vm.detail=null;vm.convert(row,"sales_order")},modifier=Modifier.fillMaxWidth()){Text("Convert to sales order") }
                    OutlinedButton(onClick = { vm.detail = null; vm.convert(row) }, modifier = Modifier.fillMaxWidth()) { Text(if (row.s("kind") == "purchase_order") "Convert to purchase bill" else "Convert to invoice") }
                }
                item { Text(vm.company.s("name"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            } }
        }
    }
}

@Composable fun DetailValue(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
    }
}
