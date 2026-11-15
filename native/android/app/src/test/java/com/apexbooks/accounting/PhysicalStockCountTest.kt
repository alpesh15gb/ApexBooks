package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApiFailure
import com.apexbooks.accounting.data.RetrySubmission
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.math.BigDecimal

class PhysicalStockCountTest {
    private val digest = "a".repeat(64)
    private fun source() = JSONObject().put("item_id", "sku-1")
        .put("date", "2026-11-15").put("on_hand", "3.125").put("stock_snapshot", digest)

    @Test fun increaseRequiresCostAndSendsServerSnapshot() {
        val snapshot = CountSnapshot.parse(source(), "sku-1")
        assertEquals(BigDecimal("0.175"), snapshot.difference("3.300"))
        assertThrows(IllegalArgumentException::class.java) { snapshot.body("3.300", "Recount", "") }
        assertThrows(IllegalArgumentException::class.java) { snapshot.body("3.300", " ", "2.50") }
        val body = snapshot.body("3.300", " Confirmed recount ", "2.50")
        assertEquals("sku-1", body.getString("item_id"))
        assertEquals(digest, body.getString("stock_snapshot"))
        assertEquals("2026-11-15", body.getString("date"))
        assertEquals("3.300", body.getString("counted_quantity"))
        assertEquals("2.50", body.getString("unit_cost"))
        assertEquals("Confirmed recount", body.getString("reason"))
    }

    @Test fun fullWriteoffOmitsCostAndMatchingCountDoesNotPost() {
        val snapshot = CountSnapshot.parse(source(), "sku-1")
        assertEquals(BigDecimal("-3.125"), snapshot.difference("0"))
        assertFalse(snapshot.body("0", "Missing stock", "42.00").has("unit_cost"))
        assertThrows(IllegalArgumentException::class.java) { snapshot.body("3.125", "Recount", "") }
        assertNull(snapshot.difference("3.1250"))
        assertNull(snapshot.difference("-1"))
        assertNull(snapshot.difference("1e4"))
        assertNull(countUnitCost("0.00"))
        assertNull(countUnitCost("0.001"))
    }

    @Test fun snapshotMustMatchItemAndCarryOnHandEvidence() {
        assertThrows(IllegalArgumentException::class.java) { CountSnapshot.parse(source(), "other") }
        assertThrows(IllegalArgumentException::class.java) { CountSnapshot.parse(source().put("stock_snapshot", "bad"), "sku-1") }
        assertThrows(IllegalArgumentException::class.java) { CountSnapshot.parse(source().put("on_hand", "-1"), "sku-1") }
    }

    @Test fun uncertainWriteReplaysTheOriginalCountWhileConflictAllowsARecount() {
        val snapshot = CountSnapshot.parse(source(), "sku-1")
        val submission = RetrySubmission()
        val first = submission.body(snapshot.body("3", "Recount", ""))
        val unavailable = ApiFailure(503, "Response unknown")
        submission.failed(unavailable)
        assertTrue(submission.unresolved)
        assertFalse(stockCountRejected(unavailable))
        assertEquals(first.toString(), submission.body(snapshot.body("2", "Different count", "")).toString())
        assertTrue(stockCountRejected(ApiFailure(409, "Refresh on-hand stock and count again")))
    }

    @Test fun advertisedStorefrontCapabilitiesReachNativeTools() {
        val features = setOf("stock_counts", "pos_require_available_stock", "pos_register_sessions")
        val response = JSONObject().put("capabilities_version", 1).put("supported_features", JSONArray(features))
        assertEquals(features, ApiCapabilities.parse(response))
    }
}
