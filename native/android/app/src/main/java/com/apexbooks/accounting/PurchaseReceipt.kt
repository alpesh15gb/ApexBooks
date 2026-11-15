package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal

private val ratePattern = Regex("[0-9]{1,13}(?:\\.[0-9]{1,2})?")
internal const val PO_REVIEW_REQUIRED = "PO_RECEIPT_REVIEW_REQUIRED"

internal fun purchaseReceivingStatus(value: String): String = when (value) {
    "open" -> "Awaiting delivery"
    "partial" -> "Partially received"
    "received" -> "Fully received"
    "converted" -> "Converted to bill"
    "unavailable" -> "Full-order billing"
    else -> "Receiving status unavailable"
}

internal fun purchaseReceiptBody(snapshot: JSONObject, orderDate: String, today: String, values: Map<String, String>): JSONObject {
    require(snapshot.s("status") in setOf("open", "partial")) { "This order has no remaining items to receive." }
    val version = snapshot.optInt("source_version", -1)
    require(version >= 0) { "Refresh this purchase order before receiving items." }
    val date = values["date"].orEmpty()
    require(date in orderDate..today && date.isNotBlank()) { "Bill date must be between the order date and today." }
    val dueDate = values["due"].orEmpty()
    require(dueDate.isBlank() || dueDate >= date) { "Due date cannot be before the bill date." }

    val selected = JSONArray()
    val indexes = mutableSetOf<Int>()
    for (line in snapshot.a("lines").objects()) {
        val index = line.optInt("line_index", -1)
        require(index in 0..99 && indexes.add(index)) { "Refresh the order's receiving lines." }
        val rawQuantity = values["quantity:$index"].orEmpty()
        if (rawQuantity.isBlank()) continue
        val quantity = countQuantity(rawQuantity)
        require(quantity != null && quantity > BigDecimal.ZERO && quantity <= line.decimal("remaining_quantity")) {
            "Enter a quantity up to the amount remaining on line ${index + 1}."
        }
        val selectedLine = JSONObject().put("line_index", index).put("quantity", quantity.toPlainString())
        val rate = values["rate:$index"].orEmpty().trim()
        if (rate.isNotEmpty()) {
            require(ratePattern.matches(rate)) { "Enter a nonnegative unit rate with up to two decimal places on line ${index + 1}." }
            selectedLine.put("rate", rate)
        }
        selected.put(selectedLine)
    }
    require(selected.length() > 0) { "Enter the quantities received in this delivery." }
    return JSONObject().put("source_version", version).put("date", date)
        .put("number", values["number"].orEmpty().trim()).put("notes", values["notes"].orEmpty().trim())
        .put("lines", selected).also { if (dueDate.isNotBlank()) it.put("due_date", dueDate) }
}
