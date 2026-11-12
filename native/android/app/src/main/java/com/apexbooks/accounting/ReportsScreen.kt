@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject

@Composable fun PartyStatementScreen(vm: AppModel, party: JSONObject) {
    val cid = vm.companyId
    var from by remember { mutableStateOf(financialStart()) }
    var to by remember { mutableStateOf(today()) }
    var apply by remember { mutableIntStateOf(0) }
    var data by remember { mutableStateOf<JSONObject?>(null) }
    var ledger by remember { mutableStateOf<JSONObject?>(null) }
    var loadedQuery by remember { mutableStateOf("") }
    var failure by remember { mutableStateOf("") }
    fun query() = "from_date=$from&to_date=$to"
    val current = query()
    fun path(extension: String = "", dates: String = current) = vm.api.company(cid, "/parties/${party.s("id")}/statement$extension?$dates")
    LaunchedEffect(cid, apply) {
        data = null; loadedQuery = ""; failure = ""
        try { require(from <= to) { "The end date must follow the start date." }; val dates = query(); data = vm.api.request(path(dates = dates)) as JSONObject
            // An older server has no ledger; the document list below still works without it.
            ledger = try { vm.api.request(vm.api.company(cid, "/parties/${party.s("id")}/ledger?$dates")) as? JSONObject } catch (e: Exception) { currentCoroutineContext().ensureActive(); null }
            loadedQuery = dates }
        catch (e: Exception) { currentCoroutineContext().ensureActive(); failure = e.message ?: "Statement could not be loaded."; if (e is ApiFailure && e.status == 401) vm.failure(e) }
    }
    Dialog(onDismissRequest = { vm.statement = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding(), color = MaterialTheme.colorScheme.background) {
            Scaffold(topBar = { TopAppBar(title = { Text("Party statement") }, navigationIcon = { IconButton(onClick = { vm.statement = null }) { Icon(Icons.Outlined.Close, "Close statement") } }) }) { padding ->
                LazyColumn(Modifier.padding(padding).fillMaxSize(), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                    item { Heading(party.s("name"), party.o("data").s("phone")) }
                    item { CustomerCreditStatus(vm,party.s("id"),today(),"0") }
                    data?.o("balances")?.let { balances ->
                        item { Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) { Metric("To collect", money(balances.s("receivable")), Modifier.weight(1f)); Metric("To pay", money(balances.s("payable")), Modifier.weight(1f)) } }
                        item { FoldSection("Advances & credits") { for (key in listOf("customer_advance", "supplier_advance", "customer_credit", "supplier_credit")) DetailValue(friendly(key), money(balances.s(key))) } }
                    }
                    item { FoldSection("Statement period") {
                        DateField("From", from, { from = it }); DateField("To", to, { to = it })
                        Button(onClick = { apply++ }, enabled = from <= to, modifier = Modifier.fillMaxWidth()) { Text("Apply dates") }
                    } }
                    item { Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        listOf("pdf", "xlsx").forEach { format -> OutlinedButton(enabled = vm.recordsReady && loadedQuery.isNotBlank() && loadedQuery == current && vm.busy == 0, onClick = { val access=vm.readStamp(); val dates = loadedQuery; vm.task { val bytes = vm.api.bytes(path(".$format", dates)); if (vm.canRead(cid,access)) { if (format == "pdf") vm.pdf = PdfView(bytes, "party-statement.pdf") else vm.files.save(bytes, "party-statement.xlsx") } } }, modifier = Modifier.weight(1f)) { Icon(if (format == "pdf") Icons.Outlined.PictureAsPdf else Icons.Outlined.Download, null, Modifier.size(18.dp)); Spacer(Modifier.width(5.dp)); Text(format.uppercase()) } }
                    } }
                    if (loadedQuery.isNotBlank() && loadedQuery != current) item { Text("Apply the selected dates to refresh this statement and its exports.", style = MaterialTheme.typography.bodySmall) }
                    if (failure.isNotBlank()) item { Message(failure, true) }
                    if (data == null && failure.isBlank()) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                    val transactions = data?.a("transactions")?.objects().orEmpty()
                    @Composable fun DocumentCard(row: JSONObject) {
                        // Close the statement before opening the document sheet so Android back is predictable.
                        Card(onClick = { vm.statement = null; vm.detail = row }, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) { Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            DetailValue(row.s("number").ifBlank { friendly(row.s("kind")) }, money(row.s("amount")))
                            Text(row.s("date") + " · " + friendly(row.s("kind")), style = MaterialTheme.typography.bodySmall)
                            if (row.has("outstanding")) Text("Outstanding ${money(row.s("outstanding"))}", style = MaterialTheme.typography.labelMedium, color = ApexGreen)
                        } }
                    }
                    val book = ledger
                    if (book != null) {
                        item { Heading("Ledger") }
                        item { Section { val opening = book.o("opening"); DetailValue("Opening balance", ledgerBalance(opening.s("amount"), opening.s("side"))) } }
                        val entries = book.a("rows").objects()
                        if (entries.isEmpty()) item { Section { Text("No entries in this period.") } }
                        items(entries, key = { it.s("id") }) { row ->
                            Card(onClick = { vm.statement = null; vm.detail = row }, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) { Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                val debit = row.s("debit")
                                DetailValue(row.s("particulars"), if (debit.isNotBlank()) ledgerBalance(debit, "Dr") else ledgerBalance(row.s("credit"), "Cr"))
                                Text(ledgerDate(row.s("date")) + " · " + row.s("voucher_type") + " " + row.s("voucher_number"), style = MaterialTheme.typography.bodySmall)
                                Text("Balance " + ledgerBalance(row.s("balance"), row.s("balance_side")), style = MaterialTheme.typography.labelMedium)
                            } }
                        }
                        item { Section {
                            val totals = book.o("totals"); val closing = book.o("closing")
                            DetailValue("Total debit", ledgerAmount(totals.s("debit")))
                            DetailValue("Total credit", ledgerAmount(totals.s("credit")))
                            DetailValue("Closing balance", ledgerBalance(closing.s("amount"), closing.s("side")))
                        } }
                        item { FoldSection("Documents, drafts and estimates") { Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            if (transactions.isEmpty()) Text("No documents in this period.")
                            transactions.forEach { DocumentCard(it) }
                        } } }
                    } else {
                        item { Heading("Transactions") }
                        if (data != null && transactions.isEmpty()) item { Section { Text("No transactions in this period.") } }
                        items(transactions, key = { it.s("id") }) { row -> DocumentCard(row) }
                    }
                }
            }
        }
    }
}
