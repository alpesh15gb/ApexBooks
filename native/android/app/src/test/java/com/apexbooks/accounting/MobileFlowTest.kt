package com.apexbooks.accounting

import org.junit.Assert.*
import org.junit.Test

class MobileFlowTest {
    @Test fun allTransactionKindsHaveStableNavigationAndCreationGroups() {
        val expected = setOf("sales_invoice", "estimate", "proforma", "payment_in", "credit_note", "pos", "purchase_bill", "payment_out", "expense", "purchase_order", "debit_note")
        assertEquals(expected, MobileNavigation.transactions.toSet())
        expected.forEach { assertEquals("transactions", MobileNavigation.tab(it)); assertTrue(MobileNavigation.group(it).contains(it)) }
        listOf("bank", "ledger", "item", "settings", "commerce").forEach { assertEquals("more", MobileNavigation.tab(it)) }
        assertEquals("reports", MobileNavigation.tab("reports"))
        assertEquals("party", MobileNavigation.tab("party"))
    }
    @Test fun documentCannotSkipMissingPartyOrInvalidDate() {
        assertNotNull(entryStepIssue(0, " ", "2026-11-02", emptyList()))
        assertNotNull(entryStepIssue(0, "Buyer", "not-a-date", emptyList()))
        assertNull(entryStepIssue(0, "Buyer", "2026-11-02", emptyList()))
    }
    @Test fun documentItemsRequireDescriptionPositiveQuantityAndNonnegativeRate() {
        assertNotNull(entryStepIssue(1, "Buyer", "2026-11-02", emptyList()))
        listOf(Triple("", "1", "100"), Triple("Service", "0", "100"), Triple("Service", "-1", "100"), Triple("Service", "abc", "100"), Triple("Service", "1", "-1"), Triple("Service", "1", "bad")).forEach { line -> assertNotNull(entryStepIssue(1, "Buyer", "2026-11-02", listOf(line))) }
        assertNull(entryStepIssue(1, "Buyer", "2026-11-02", listOf(Triple("Free sample", "0.5", "0"), Triple("Service", "1", "100.50"))))
    }
}
