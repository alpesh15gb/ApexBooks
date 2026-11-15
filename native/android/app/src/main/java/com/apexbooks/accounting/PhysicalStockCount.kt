package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApiFailure
import org.json.JSONObject
import java.math.BigDecimal

private val quantityPattern = Regex("[0-9]{1,12}(?:\\.[0-9]{1,3})?")
private val costPattern = Regex("[0-9]{1,13}(?:\\.[0-9]{1,2})?")
private val stockDigestPattern = Regex("[0-9a-f]{64}")
private val businessDatePattern = Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}")

internal fun countQuantity(value: String): BigDecimal? =
    value.trim().takeIf(quantityPattern::matches)?.toBigDecimalOrNull()

internal fun countUnitCost(value: String): BigDecimal? =
    value.trim().takeIf(costPattern::matches)?.toBigDecimalOrNull()?.takeIf { it.signum() > 0 }

internal data class CountSnapshot(
    val itemId: String,
    val date: String,
    val onHand: BigDecimal,
    val digest: String,
) {
    fun difference(counted: String): BigDecimal? = countQuantity(counted)?.subtract(onHand)

    fun body(counted: String, reason: String, cost: String): JSONObject {
        val quantity = requireNotNull(countQuantity(counted)) { "Enter a nonnegative counted quantity." }
        val direction = quantity.compareTo(onHand)
        require(direction != 0) { "Count matches on-hand stock." }
        require(reason.trim().isNotEmpty()) { "Enter a reason for the count difference." }
        val result = JSONObject()
            .put("item_id", itemId)
            .put("date", date)
            .put("stock_snapshot", digest)
            .put("counted_quantity", quantity.toPlainString())
            .put("reason", reason.trim())
        if (direction > 0) {
            val unitCost = requireNotNull(countUnitCost(cost)) { "Enter the reviewed cost per unit." }
            result.put("unit_cost", unitCost.toPlainString())
        }
        return result
    }

    companion object {
        fun parse(value: JSONObject, itemId: String): CountSnapshot {
            val date = value.optString("date")
            val digest = value.optString("stock_snapshot")
            val onHand = countQuantity(value.optString("on_hand"))
            require(itemId.isNotBlank() && value.optString("item_id") == itemId &&
                businessDatePattern.matches(date) && stockDigestPattern.matches(digest) && onHand != null) {
                "The server did not return a valid on-hand snapshot for this item."
            }
            return CountSnapshot(itemId, date, onHand, digest)
        }
    }
}

// The count endpoint looks up the exact retry key before checking the current
// date or stock snapshot, so a 409 definitively rejects this count.
internal fun stockCountRejected(error: Exception): Boolean = error is ApiFailure && error.status == 409
