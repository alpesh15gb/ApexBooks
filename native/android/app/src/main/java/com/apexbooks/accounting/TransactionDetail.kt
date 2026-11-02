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
    LaunchedEffect(cid, initial.s("id"), vm.revision) {
        record = null; failure = ""
        try { record = vm.api.record(cid, initial.s("id")) }
        catch (e: Exception) { currentCoroutineContext().ensureActive(); failure = e.message ?: "Could not load this transaction."; if (e is ApiFailure && e.status == 401) vm.failure(e) }
    }
    val row = record ?: initial
    val data = row.o("data")
    val editable = vm.canWrite && record != null && row.s("converted_to").isBlank() && row.s("kind") in (vm.documentKinds + setOf("payment_in", "payment_out", "item", "party"))
    val printable = record != null && row.s("kind") in (vm.documentKinds + setOf("payment_in", "payment_out", "customer_refund", "supplier_refund", "advance_refund", "advance_application", "credit_application"))
    Dialog(onDismissRequest = { vm.detail = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding(), color = MaterialTheme.colorScheme.background) {
            Scaffold(topBar = { TopAppBar(title = { Text(friendly(row.s("kind"))) }, navigationIcon = { IconButton(onClick = { vm.detail = null }) { Icon(Icons.Outlined.Close, "Close transaction") } }) }, bottomBar = {
                Surface(shadowElevation = 8.dp) { Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (printable) OutlinedButton(onClick = { vm.documentPdf(row) }, modifier = Modifier.weight(1f)) { Icon(Icons.Outlined.PictureAsPdf, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("PDF / share") }
                    if (editable) Button(onClick = { vm.detail = null; vm.edit(row) }, modifier = Modifier.weight(1f)) { Icon(Icons.Outlined.Edit, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Edit") }
                } }
            }) { padding -> LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                if (record == null && failure.isBlank()) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                if (failure.isNotBlank()) item { Message(failure, true) }
                item { Section {
                    StatusPill(registerStatus(row))
                    Text(row.s("number").ifBlank { friendly(row.s("kind")) }, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text(row.s("name"), style = MaterialTheme.typography.bodyLarge)
                    Text(money(row.s("amount")), style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold, color = ApexGreen)
                    DetailValue("Date", row.s("date"))
                    if (data.s("due_date").isNotBlank()) DetailValue("Due date", data.s("due_date"))
                    if (row.has("outstanding") && !row.isNull("outstanding")) DetailValue("Outstanding", money(row.s("outstanding")))
                    if (row.s("converted_to").isNotBlank()) Text("Converted to a posted document", color = ApexGreen)
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
                itemsIndexed(data.a("lines").objects()) { index, line -> Section {
                    Text("${index + 1}. ${line.s("description")}", fontWeight = FontWeight.SemiBold)
                    DetailValue("${line.s("quantity")} ${line.s("unit")} × ${money(line.s("rate"))}", money(line.decimal("taxable") + line.decimal("tax")))
                    if (vm.regular || line.decimal("tax").signum() != 0) DetailValue("GST ${line.s("gst_rate")}%", money(line.s("tax")))
                } }
                if (data.s("notes").isNotBlank()) item { Section("Notes") { Text(data.s("notes")) } }
                if (data.s("terms").isNotBlank()) item { Section("Terms") { Text(data.s("terms")) } }
                if (vm.canWrite && row.s("kind") in vm.draftKinds && row.s("converted_to").isBlank() && record != null) item {
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
