package com.apexbooks.accounting

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.math.BigDecimal

class PosCounterTest {
    private fun product(name: String, barcode: String) =
        JSONObject().put("name", name).put("data", JSONObject().put("barcode", barcode))

    @Test fun exactBarcodeTakesPriorityWithoutDroppingZeros() {
        val item = product("Cable", "00123")
        val other = product("00123", "")
        assertEquals(listOf(item), exactPosMatches(listOf(other, item), " 00123 ", false))
        assertTrue(exactPosMatches(listOf(item), "123", false).isEmpty())
        assertTrue(exactPosMatches(listOf(item), "Cable", true).isEmpty())
        assertEquals(listOf(item), exactPosMatches(listOf(item), "cable", false))
    }

    @Test fun duplicateBarcodeRequiresExplicitSelection() {
        val products = listOf(product("First", "123"), product("Second", "123"))
        assertNull(exactPosMatches(products, "123", true).singleOrNull())
        assertEquals(2, exactPosMatches(products, "123", true).size)
    }

    @Test fun splitCalculatesCashAndRejectsInvalidBankPortions() {
        val total = BigDecimal("250.00")
        assertEquals(BigDecimal("149.50"), posCashDue(total, "split", "100.50"))
        assertNull(posCashDue(total, "split", "0"))
        assertNull(posCashDue(total, "split", "250.00"))
        assertNull(posCashDue(total, "split", "100.501"))
        assertNull(posMoneyInput("-1.00"))
    }
}
