package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import org.json.JSONArray
import org.json.JSONObject

/** Formatted Profit & Loss and Balance Sheet from /reports/statements. All figures are server-calculated. */
@Composable fun StatementsContent(data: JSONObject) {
    val pl = data.o("profit_loss")
    val bs = data.o("balance_sheet")
    Section("Profit and loss") {
        Text("${data.s("from_date")} to ${data.s("to_date")}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        StatementHeading("Revenue")
        StatementLines(pl.o("revenue").a("lines"), "No sales in this period")
        StatementRow("Total revenue", pl.o("revenue").s("total"), bold = true)
        StatementHeading("Cost of sales")
        StatementLines(pl.o("cost_of_sales").a("lines"), "No cost of sales")
        StatementRow("Total cost of sales", pl.o("cost_of_sales").s("total"), bold = true)
        HorizontalDivider()
        StatementRow("Gross profit", pl.s("gross_profit"), bold = true)
        if (pl.has("gross_margin_percent") && !pl.isNull("gross_margin_percent")) Text("${pl.s("gross_margin_percent")}% of revenue", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (pl.o("other_income").a("lines").length() > 0) {
            StatementHeading("Other income")
            StatementLines(pl.o("other_income").a("lines"), "")
            StatementRow("Total other income", pl.o("other_income").s("total"), bold = true)
        }
        StatementHeading("Operating expenses")
        StatementLines(pl.o("operating_expenses").a("lines"), "No expenses recorded")
        StatementRow("Total operating expenses", pl.o("operating_expenses").s("total"), bold = true)
        HorizontalDivider(thickness = 2.dp)
        StatementRow(if ((pl.s("net_profit").toBigDecimalOrNull() ?: java.math.BigDecimal.ZERO).signum() < 0) "Net loss" else "Net profit", pl.s("net_profit"), bold = true, large = true)
    }
    Section("Balance sheet") {
        Text("As of ${bs.s("as_of")}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        StatementHeading("Assets")
        StatementSections(bs.o("assets").a("sections"))
        StatementRow("Total assets", bs.o("assets").s("total"), bold = true)
        StatementHeading("Liabilities")
        StatementSections(bs.o("liabilities").a("sections"))
        StatementRow("Total liabilities", bs.o("liabilities").s("total"), bold = true)
        StatementHeading("Equity")
        StatementLines(bs.o("equity").a("lines"), "")
        StatementRow("Total equity", bs.o("equity").s("total"), bold = true)
        HorizontalDivider(thickness = 2.dp)
        StatementRow("Total liabilities and equity", bs.s("total_liabilities_and_equity"), bold = true, large = true)
        val balanced = (bs.s("difference").toBigDecimalOrNull() ?: java.math.BigDecimal.ONE).signum() == 0
        Text(
            if (balanced) "Balance sheet balances: assets equal liabilities plus equity." else "Out of balance by ${money(bs.s("difference"))}. Do not rely on these figures.",
            style = MaterialTheme.typography.bodySmall, color = if (balanced) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
        )
    }
    Section { Text(data.s("basis") + " Depreciation, net realisable value write-downs and accruals are not calculated; review with your accountant before using these statements for filing or lending.", style = MaterialTheme.typography.bodySmall) }
}

@Composable private fun StatementHeading(text: String) {
    Spacer(Modifier.height(6.dp))
    Text(text.uppercase(), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, fontWeight = FontWeight.Bold)
}

@Composable private fun StatementRow(label: String, value: String, bold: Boolean = false, large: Boolean = false, indent: Boolean = false) {
    Row(Modifier.fillMaxWidth().padding(start = if (indent) 14.dp else 0.dp), verticalAlignment = Alignment.Top) {
        Text(label, Modifier.weight(1f), style = if (large) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium, fontWeight = if (bold) FontWeight.SemiBold else FontWeight.Normal)
        Spacer(Modifier.width(12.dp))
        Text(money(value), style = if (large) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium, fontWeight = if (bold) FontWeight.SemiBold else FontWeight.Normal)
    }
}

@Composable private fun StatementLines(lines: JSONArray, emptyText: String) {
    val items = lines.objects()
    if (items.isEmpty() && emptyText.isNotBlank()) Text(emptyText, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    items.forEach { StatementRow(it.s("name"), it.s("amount"), indent = true) }
}

@Composable private fun StatementSections(sections: JSONArray) {
    val items = sections.objects()
    if (items.isEmpty()) Text("None", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    items.forEach { section ->
        StatementRow(section.s("label"), section.s("total"), bold = true)
        val lines = section.a("lines").objects()
        if (lines.size > 1) lines.forEach { StatementRow(it.s("name"), it.s("amount"), indent = true) }
    }
}
