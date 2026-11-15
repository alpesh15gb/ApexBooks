package com.apexbooks.accounting

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class PurchaseReceiptTest {
    private val day = "2026-11-15"
    private val orderDate = "2026-11-14"
    private fun review(status: String = "partial") = JSONObject()
        .put("source_version", 3)
        .put("status", status)
        .put("lines", JSONArray()
            .put(JSONObject().put("line_index", 0).put("description", "Cable").put("remaining_quantity", "3.125"))
            .put(JSONObject().put("line_index", 1).put("description", "Cable").put("remaining_quantity", "0.500")))

    @Test fun deliveryKeepsSameItemRowsDistinctAndUsesExplicitRateOverride() {
        val values = mapOf("date" to day, "number" to " SUP-1 ", "due" to "2026-12-01",
            "quantity:0" to "2.750", "quantity:1" to "0.125", "rate:1" to "7.25")
        val body = purchaseReceiptBody(review(), orderDate, day, values)
        val lines = body.getJSONArray("lines")
        assertEquals(3, body.getInt("source_version"))
        assertEquals("SUP-1", body.getString("number"))
        assertEquals("2026-12-01", body.getString("due_date"))
        assertEquals(2, lines.length())
        assertEquals(0, lines.getJSONObject(0).getInt("line_index"))
        assertEquals("2.750", lines.getJSONObject(0).getString("quantity"))
        assertFalse(lines.getJSONObject(0).has("rate"))
        assertEquals(1, lines.getJSONObject(1).getInt("line_index"))
        assertEquals("7.25", lines.getJSONObject(1).getString("rate"))
        assertFalse(body.has("expected_total"))
    }

    @Test fun invalidCapacityDatesAndAmountsNeverQuote() {
        val values = mapOf("date" to day, "quantity:0" to "3.125")
        for (changed in listOf(
            mapOf("quantity:0" to "3.126"), mapOf("quantity:0" to "3.1250"),
            mapOf("quantity:0" to "0"), mapOf("rate:0" to "0.001"),
            mapOf("date" to "2026-11-13"), mapOf("date" to "2026-11-16"),
            mapOf("due" to "2026-11-14"),
        )) assertThrows(IllegalArgumentException::class.java) {
            purchaseReceiptBody(review(), orderDate, day, values + changed)
        }
        assertThrows(IllegalArgumentException::class.java) { purchaseReceiptBody(review("received"), orderDate, day, values) }
        assertThrows(IllegalArgumentException::class.java) { purchaseReceiptBody(review("converted"), orderDate, day, values) }
    }
}
