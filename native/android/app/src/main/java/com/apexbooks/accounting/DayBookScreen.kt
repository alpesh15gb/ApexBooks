package com.apexbooks.accounting

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import java.time.LocalDate

private val MoneyIn = Color(0xFF1F7A4D)
private val MoneyOut = Color(0xFFB42318)

/** Day book (Vyapar / MyBillBook style): everything dated one day, with the cash and bank it moved. */
@Composable fun DayBookScreen(vm: AppModel) {
    var day by remember { mutableStateOf(today()) }
    var book by remember { mutableStateOf<JSONObject?>(null) }
    LaunchedEffect(vm.companyId, vm.revision, day) {
        book = null
        if (!vm.supports("day_book")) return@LaunchedEffect
        try { book = vm.api.request(vm.api.company(vm.companyId, "/day-book?day=$day")) as JSONObject }
        catch (e: Exception) { currentCoroutineContext().ensureActive(); vm.failure(e) }
    }
    fun shift(days: Long) { day = LocalDate.parse(day).plusDays(days).toString() }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                IconButton(onClick = { shift(-1) }) { Icon(Icons.AutoMirrored.Outlined.KeyboardArrowLeft, "Previous day") }
                Text(if (day == today()) "Today · $day" else day, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                if (day != today()) TextButton(onClick = { day = today() }) { Text("Today") }
                IconButton(onClick = { shift(1) }) { Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, "Next day") }
            }
        }
        if (!vm.supports("day_book")) { item { Section { Text("The day book needs an updated Apex Books server. Your records are unaffected.") } }; return@LazyColumn }
        val current = book
        if (current == null) { item { LinearProgressIndicator(Modifier.fillMaxWidth()) }; return@LazyColumn }
        val totals = current.o("totals")
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Metric("Money in", money(totals.s("money_in")), Modifier.weight(1f))
                Metric("Money out", money(totals.s("money_out")), Modifier.weight(1f))
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Metric("Sales", money(totals.s("sales")), Modifier.weight(1f))
                Metric("Purchases & expenses", money(totals.decimal("purchases") + totals.decimal("expenses")), Modifier.weight(1f))
            }
        }
        val rows = current.a("rows").objects()
        if (rows.isEmpty()) item { Section { Text("Nothing recorded on this day.", color = MaterialTheme.colorScheme.onSurfaceVariant) } }
        items(rows, key = { it.s("id") }) { row ->
            val kind = row.s("kind")
            val record = if (kind == "journal") null else vm.records.find { it.s("id") == row.s("id") }
            Card(Modifier.fillMaxWidth().then(if (record != null) Modifier.clickable { vm.detail = record } else Modifier),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Row(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(listOf(row.s("number"), row.s("name")).filter { it.isNotBlank() }.joinToString(" · "), fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        val state = if (row.optBoolean("cancelled")) " · cancelled" else if (!row.optBoolean("posted") && kind != "journal") " · draft" else ""
                        Text(vm.title(kind) + state + " · " + money(row.s("amount")), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    val moneyIn = row.decimal("money_in"); val moneyOut = row.decimal("money_out")
                    if (moneyIn.signum() > 0) Text("+" + money(moneyIn), color = MoneyIn, fontWeight = FontWeight.SemiBold)
                    else if (moneyOut.signum() > 0) Text("−" + money(moneyOut), color = MoneyOut, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}
