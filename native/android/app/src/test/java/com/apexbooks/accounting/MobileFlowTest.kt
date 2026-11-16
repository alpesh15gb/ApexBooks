package com.apexbooks.accounting

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MobileFlowTest {
    @org.junit.Test fun selectionLabelsExposeVisibleContextAndValue(){
        org.junit.Assert.assertEquals("Saved party · Enter manually",selectionDescription("Saved party","Enter manually"))
        org.junit.Assert.assertEquals("Item / service · Synthetic item",selectionDescription("Item / service","Synthetic item"))
        org.junit.Assert.assertEquals("Due date · optional · Not set",selectionDescription("Due date · optional",""))
    }

    @Test fun allTransactionKindsHaveStableNavigationAndCreationGroups() {
        val expected = setOf("sales_invoice", "estimate", "proforma", "sales_order", "payment_in", "credit_note", "pos", "purchase_bill", "payment_out", "expense", "purchase_order", "debit_note")
        assertEquals(expected, MobileNavigation.transactions.toSet())
        expected.forEach {
            assertEquals(if (it == "pos") "pos" else "transactions", MobileNavigation.tab(it))
            assertTrue(MobileNavigation.group(it).contains(it))
        }
        listOf("bank", "ledger", "item", "settings", "commerce", "party").forEach { assertEquals("more", MobileNavigation.tab(it)) }
        assertEquals("reports", MobileNavigation.tab("reports"))
        assertEquals(listOf("Home", "POS", "Entries", "Reports", "More"), MobileNavigation.primary.map { it.second })
        assertEquals("purchase_order", MobileNavigation.entryDestination("purchase_order"))
        assertEquals("sales_invoice", MobileNavigation.entryDestination("pos"))
    }

    @Test fun widerWindowsUseLeadingNavigationWithRoomForTheFiveDestinations() {
        assertFalse(MobileNavigation.usesRail(599f, 900f))
        assertFalse(MobileNavigation.usesRail(700f, 320f))
        assertTrue(MobileNavigation.usesRail(600f, 380f))
        assertTrue(MobileNavigation.usesRail(900f, 1024f))
    }

    @Test fun companySearchPromotesExactBarcodesBeforePartialNamesAndCodes() {
        val similar = JSONObject("""{"kind":"item","name":"Code 00012345 pouch","data":{"barcode":"000123459"}}""")
        val exact = JSONObject("""{"kind":"item","name":"Counter cable","data":{"barcode":"00012345","hsn":"8544"}}""")
        val party = JSONObject("""{"kind":"party","name":"Retail buyer","data":{"phone":"9000000901"}}""")
        assertEquals(listOf(exact, similar), searchWorkspaceRecords(listOf(similar, party, exact), "00012345"))
        assertEquals(listOf(party), searchWorkspaceRecords(listOf(exact, party), "9000000901"))
        assertEquals(emptyList<JSONObject>(), searchWorkspaceRecords(listOf(exact), " "))
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
