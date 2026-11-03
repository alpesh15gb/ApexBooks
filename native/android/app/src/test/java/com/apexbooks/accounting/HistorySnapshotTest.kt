package com.apexbooks.accounting

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class HistorySnapshotTest {
    private val first=Instant.parse("2026-11-03T10:00:00Z")
    @Test fun completeLoadIsExplicitlyNotLive(){
        val state=HistorySnapshot().completed(first,true)
        assertEquals(first,state.loadedAt);assertFalse(state.refreshFailed)
        assertTrue(state.label().contains("15:30:00 IST"));assertTrue(state.label().contains("not live"))
    }
    @Test fun failedRefreshRetainsOriginalLoadTimeUntilSuccessfulRefresh(){
        val prior=HistorySnapshot().completed(first,true)
        val failed=prior.failed(true)
        assertEquals(first,failed.loadedAt);assertTrue(failed.refreshFailed)
        assertTrue(failed.label().contains("prior history"))
        val recovered=failed.completed(first.plusSeconds(60),true)
        assertFalse(recovered.refreshFailed);assertEquals(first.plusSeconds(60),recovered.loadedAt)
    }
    @Test fun obsoleteCompanySessionOrSequenceCannotChangeSnapshot(){
        val current=HistorySnapshot().completed(first,true)
        assertSame(current,current.failed(false))
        assertSame(current,current.completed(first.plusSeconds(60),false))
        val replacement=HistorySnapshot()
        assertSame(replacement,replacement.failed(false))
        assertSame(replacement,replacement.completed(first,false))
        assertNull(replacement.loadedAt)
    }
    @Test fun initialFailureNeverClaimsLoadedHistory(){
        val state=HistorySnapshot().failed(true)
        assertTrue(state.refreshFailed);assertNull(state.loadedAt)
        assertTrue(state.label().contains("not loaded"))
    }
}
