package com.apexbooks.accounting

/** Stable destinations shared by the mobile shell, transaction filters and create sheet. */
object MobileNavigation {
    val sales = listOf("sales_invoice", "estimate", "proforma", "sales_order", "payment_in", "credit_note", "pos")
    val purchases = listOf("purchase_bill", "payment_out", "expense", "purchase_order", "debit_note")
    val transactions = sales + purchases
    fun tab(page: String) = when (page) {
        "dashboard", "party", "reports" -> page
        in transactions -> "transactions"
        else -> "more"
    }
    fun group(page: String) = if (page in purchases) purchases else sales
}

/** Local step validation improves navigation; the API remains authoritative on save. */
fun entryStepIssue(step: Int, name: String, date: String, lines: List<Triple<String, String, String>>): String? {
    if (step == 0) {
        if (name.isBlank()) return "Choose a party or enter a customer / supplier name."
        if (runCatching { java.time.LocalDate.parse(date) }.isFailure) return "Choose a valid document date."
    }
    if (step == 1) {
        if (lines.isEmpty()) return "Add at least one item or service."
        lines.forEachIndexed { index, (description, quantity, rate) ->
            if (description.isBlank()) return "Enter a description for item ${index + 1}."
            if (quantity.toBigDecimalOrNull()?.signum() != 1) return "Enter a quantity greater than zero for item ${index + 1}."
            val price = rate.toBigDecimalOrNull()
            if (price == null || price.signum() < 0) return "Enter a valid rate for item ${index + 1}."
        }
    }
    return null
}
