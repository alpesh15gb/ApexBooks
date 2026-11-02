@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.apexbooks.accounting

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import org.json.JSONObject
import java.math.BigDecimal

@Composable fun RegisterScreen(vm: AppModel) {
    var search by remember(vm.companyId, vm.page) { mutableStateOf("") }
    var period by remember(vm.companyId, vm.page) { mutableStateOf("all") }
    var start by remember(vm.companyId, vm.page) { mutableStateOf(financialStart()) }
    var end by remember(vm.companyId, vm.page) { mutableStateOf(today()) }
    var party by remember(vm.companyId, vm.page) { mutableStateOf("all") }
    var status by remember(vm.companyId, vm.page) { mutableStateOf("all") }
    var sort by remember(vm.companyId, vm.page) { mutableStateOf("new") }
    var filters by remember { mutableStateOf(false) }
    var count by remember(vm.companyId, vm.page) { mutableIntStateOf(50) }
    val master = vm.page in setOf("party", "item")
    val transaction = vm.page in MobileNavigation.transactions
    val from = when (period) { "month" -> today().take(7) + "-01"; "fy" -> financialStart(); "custom" -> start; else -> "" }
    val to = if (period == "all") "" else if (period == "custom") end else today()
    val filtered=search.isNotBlank()||period!="all"||party!="all"||status!="all"
    val rows = filterRegister(vm.records, vm.page, search, from, to, party, status, sort)
    LaunchedEffect(search, period, start, end, party, status, sort) { count = 50 }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 100.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (transaction) item {
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                listOf("Sales", "Purchase").forEachIndexed { index, label -> SegmentedButton(selected = (vm.page in MobileNavigation.purchases) == (index == 1), onClick = { vm.navigate(if (index == 0) "sales_invoice" else "purchase_bill") }, shape = SegmentedButtonDefaults.itemShape(index, 2)) { Text(label) } }
            }
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MobileNavigation.group(vm.page).forEach { key -> FilterChip(selected = vm.page == key, onClick = { vm.navigate(key) }, label = { Text(vm.title(key)) }) }
            }
        }
        item { Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.weight(1f)) { SearchBarField(if (master) "Search name, phone or barcode" else "Search party or reference", search) { search = it } }
            FilledTonalIconButton(onClick = { filters = true }, modifier = Modifier.size(52.dp), shape = RoundedCornerShape(16.dp)) { Icon(Icons.Outlined.Tune, "Filter and sort") }
        } }
        if(filtered)item { Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.SpaceBetween) {
            Text("Filtered · ${rows.size} results",style=MaterialTheme.typography.labelMedium)
            TextButton(onClick={search="";period="all";party="all";status="all"}){Text("Clear filters")}
        } }
        if(period=="custom"&&start>end)item{Message("The start date must be on or before the end date.",true)}
        if (!master) item {
            val total = rows.fold(BigDecimal.ZERO) { sum, row -> sum + row.decimal("amount") }
            Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(20.dp)) { Row(Modifier.fillMaxWidth().padding(18.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Column { Text("${rows.size} ${if (rows.size == 1) "transaction" else "transactions"}", style = MaterialTheme.typography.labelMedium); Text(money(total), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = ApexGreen) }
                if (vm.page in setOf("sales_invoice", "purchase_bill")) Column(horizontalAlignment = Alignment.End) { Text("Outstanding", style = MaterialTheme.typography.labelMedium); Text(money(rows.fold(BigDecimal.ZERO) { sum, row -> sum + row.decimal("outstanding") }), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold) }
            } }
        } else item { Text("${rows.size} ${if (vm.page == "party") "parties · tap for statement" else "items"}", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        if (vm.page == "item" && vm.canWrite) item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { AssistChip(onClick = { vm.tool = "stock_opening" }, label = { Text("Opening stock") }); AssistChip(onClick = { vm.tool = "stock_adjust" }, label = { Text("Adjust stock") }) } }
        if (vm.canWrite && vm.page in setOf("payment_in", "payment_out", "credit_note", "debit_note")) item { AssistChip(onClick = { vm.tool = if (vm.page in setOf("credit_note", "debit_note")) "settle_credit" else "settle_advance" }, label = { Text("Apply / refund balance") }) }
        if (rows.isEmpty()) item { Column(Modifier.fillMaxWidth().padding(vertical = 32.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(featureIcon(vm.page), null, Modifier.size(52.dp), tint = ApexGreen)
            Text(if (search.isBlank() && period == "all" && status == "all") "No ${vm.title(vm.page).lowercase()} yet" else "No matching records", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Text(if(!vm.canWrite)"You have read-only access. Adjust filters or ask an owner to add records."else if(filtered)"Clear or adjust filters to see your records."else"Create your first record to start this register.", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
            if (vm.canWrite) Button(onClick = { vm.add(vm.page) }) { Text("Add ${if (vm.page == "party") "party" else if (vm.page == "item") "item" else "transaction"}") }
        } }
        items(rows.take(count), key = { it.s("id") }) { RecordCard(vm, it) }
        if (rows.size > count) item { OutlinedButton(onClick = { count += 50 }, modifier = Modifier.fillMaxWidth()) { Text("Show more · ${count} of ${rows.size}") } }
    }
    if (filters) ModalBottomSheet(onDismissRequest = { filters = false }) { Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Heading("Filter & sort")
        if (!master) {
            Choice("Period", period, listOf("all" to "All dates", "month" to "This month", "fy" to "Financial year", "custom" to "Custom dates"), { period = it })
            if (period == "custom") { DateField("From", start, { start = it }); DateField("To", end, { end = it }) }
            Choice("Party", party, listOf("all" to "All parties") + vm.records.filter { it.s("kind") == vm.page }.map { it.s("name") }.distinct().sorted().map { it to it }, { party = it })
            Choice("Status", status, listOf("all" to "All statuses") + listOf("Unpaid", "Part settled", "Settled", "Draft", "Converted", "Posted", "Advance available", "Advance settled", "Credit available", "Credit settled").map { it to it }, { status = it })
        }
        if(master)Choice("Status",status,listOf("all" to "All masters","Active" to "Active","Inactive" to "Inactive"),{status=it})
        Choice("Sort", sort, listOf("new" to "Newest first", "old" to "Oldest first", "name" to "Name A–Z", "amount" to "Highest amount"), { sort = it })
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) { OutlinedButton(onClick = { period = "all"; party = "all"; status = "all"; sort = "new"; search = "" }, modifier = Modifier.weight(1f)) { Text("Reset") }; Button(onClick = { filters = false }, modifier = Modifier.weight(1f)) { Text("Show ${rows.size} records") } }
        Spacer(Modifier.height(24.dp))
    } }
}

@Composable fun StatusPill(status: String) {
    val color = when (status) { "Unpaid" -> Color(0xFFAC650D); "Part settled" -> Color(0xFF6854BA); "Draft" -> Color(0xFF64748B); else -> Color(0xFF147D64) }
    Surface(color = color.copy(alpha = .09f), shape = RoundedCornerShape(8.dp)) { Text(status, Modifier.padding(horizontal = 8.dp, vertical = 4.dp), style = MaterialTheme.typography.labelMedium, color = color, fontWeight = FontWeight.SemiBold) }
}

@Composable fun RecordCard(vm: AppModel, row: JSONObject) {
    val kind = row.s("kind"); val master = kind in setOf("party", "item")
    Card(onClick = { when { kind == "party" -> vm.statement = row; kind == "item" && vm.canWrite -> vm.edit(row); else -> vm.detail = row } }, shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (kind == "item") DataImage(row.o("data").s("image_thumbnail"), Modifier.size(48.dp))
                else Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(14.dp)) { if (kind == "party") Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) { Text(row.s("name").take(1).uppercase(), color = ApexGreen, fontWeight = FontWeight.Bold) } else Icon(featureIcon(kind), null, Modifier.padding(12.dp).size(20.dp), tint = ApexGreen) }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(row.s("name"), maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyLarge)
                    Text(if (master) row.o("data").s(if (kind == "party") "phone" else "hsn").ifBlank { if (kind == "party") "View transactions & balances" else "View item details" } else row.s("number") + " · " + row.s("date"), maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (!master || kind == "item") Text(money(if (kind == "item") row.o("data").s("sale_rate") else row.s("amount")), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                else Icon(Icons.Outlined.ChevronRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if(master)StatusPill(registerStatus(row))
            if (!master) Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                StatusPill(registerStatus(row))
                if (row.has("outstanding") && !row.isNull("outstanding")) Text("Due ${money(row.s("outstanding"))}", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
