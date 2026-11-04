package com.apexbooks.accounting

import android.content.Context
import android.content.Intent
import android.net.Uri
import com.apexbooks.accounting.data.*
import org.json.JSONObject

/** WhatsApp share and payment-reminder text, matching the web and Windows wording. Nothing is sent until the user presses send. */
object WhatsAppShare {
    private val titles = mapOf("sales_invoice" to "Invoice", "pos" to "Bill", "estimate" to "Estimate", "proforma" to "Proforma invoice", "sales_order" to "Sales order", "credit_note" to "Credit note", "payment_in" to "Payment receipt", "purchase_order" to "Purchase order")
    fun shareable(kind: String) = kind in titles
    fun canRemind(row: JSONObject) = row.s("kind") in setOf("sales_invoice", "pos") && row.optBoolean("posted") && !row.optBoolean("cancelled") && row.decimal("outstanding").signum() > 0

    fun phone(value: String): String {
        val digits = value.filter(Char::isDigit).trimStart('0')
        return if (digits.length == 10) "91$digits" else if (digits.length in 11..15) digits else ""
    }

    fun documentMessage(row: JSONObject, company: String, upi: String): String {
        val data = row.o("data"); val lines = mutableListOf("Dear ${row.s("name").ifBlank { "Customer" }},", "${titles[row.s("kind")] ?: "Document"} ${row.s("number")} dated ${row.s("date")} for ${money(row.s("amount"))} from $company.")
        if (row.s("kind") in setOf("sales_invoice", "pos") && row.optBoolean("posted")) {
            val due = row.decimal("outstanding")
            lines += if (due.signum() > 0) "Balance due: ${money(due)}" + data.s("due_date").takeIf { it.isNotBlank() }?.let { " by $it" }.orEmpty() + "." else "Fully paid. Thank you!"
            if (due.signum() > 0 && upi.isNotBlank()) lines += "Pay by UPI: $upi"
        }
        lines += "Thank you for your business."
        return lines.joinToString("\n")
    }

    fun reminderMessage(row: JSONObject, company: String, upi: String, today: String = today()): String {
        val due = row.o("data").s("due_date"); val overdue = due.isNotBlank() && due < today
        val lines = mutableListOf("Dear ${row.s("name").ifBlank { "Customer" }},", "This is a gentle reminder that ${money(row.s("outstanding"))} is ${if (overdue) "overdue since $due" else "pending"} against ${titles[row.s("kind")] ?: "invoice"} ${row.s("number")} dated ${row.s("date")}.")
        if (upi.isNotBlank()) lines += "You can pay by UPI: $upi"
        lines += "Please ignore if already paid.\n– $company"
        return lines.joinToString("\n")
    }

    class OverdueGroup(val name: String, val phone: String, val invoices: List<JSONObject>, val total: java.math.BigDecimal)
    /** "Remind all overdue": one group per customer, largest overdue balance first. */
    fun overdueByParty(records: List<JSONObject>, today: String = today()): List<OverdueGroup> {
        fun phoneFor(invoice: JSONObject) = records.firstOrNull { it.s("kind") == "party" && (it.s("id") == invoice.o("data").s("party_id") || it.s("name").trim().equals(invoice.s("name").trim(), true)) }?.o("data")?.s("phone")?.takeIf { it.isNotBlank() } ?: invoice.o("data").s("party_phone")
        return records.filter { canRemind(it) && it.o("data").s("due_date").let { due -> due.isNotBlank() && due < today } }
            .groupBy { it.s("name").trim().lowercase() }.values
            .map { group -> OverdueGroup(group.first().s("name"), group.map(::phoneFor).firstOrNull { it.isNotBlank() } ?: "", group, group.fold(java.math.BigDecimal.ZERO) { sum, r -> sum + r.decimal("outstanding") }) }
            .sortedByDescending { it.total }
    }
    fun partyReminderMessage(group: OverdueGroup, company: String, upi: String): String {
        val lines = mutableListOf("Dear ${group.name.ifBlank { "Customer" }},", "This is a gentle reminder that ${money(group.total)} is overdue:")
        group.invoices.forEach { lines += "• ${titles[it.s("kind")] ?: "Invoice"} ${it.s("number")} dated ${it.s("date")}: ${money(it.s("outstanding"))} (due ${it.o("data").s("due_date")})" }
        if (upi.isNotBlank()) lines += "You can pay by UPI: $upi"
        lines += "Please ignore if already paid.\n– $company"
        return lines.joinToString("\n")
    }

    fun open(context: Context, phone: String, text: String) {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/${phone(phone)}?text=${Uri.encode(text)}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
