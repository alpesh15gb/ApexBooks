package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.junit.Assert.*
import org.junit.Test

class AmountPrivacyTest {
    @Test fun hiddenAmountsShowOneFixedMaskThatRevealsNothing() {
        assertEquals(AmountPrivacy.MASK, AmountPrivacy.text(true, "₹98,76,543.21"))
        assertEquals(AmountPrivacy.MASK, AmountPrivacy.text(true, "-₹5.00"))
        assertEquals("₹5.00", AmountPrivacy.text(false, "₹5.00"))
        assertTrue("The mask must not reveal size", AmountPrivacy.MASK.none { it.isDigit() })
    }

    @Test fun onlyAMissingEndpointSkipsThePasswordCheck() {
        assertTrue(AmountPrivacy.revealUnsupported(ApiFailure(404, "Not found")))
        assertTrue(AmountPrivacy.revealUnsupported(ApiFailure(405, "Method not allowed")))
        for (status in listOf(0, 401, 403, 422, 429, 500)) assertFalse("status $status", AmountPrivacy.revealUnsupported(ApiFailure(status, "x")))
        assertFalse(AmountPrivacy.revealUnsupported(IllegalStateException("boom")))
    }

    @Test fun failuresExplainThemselvesWithoutRevealing() {
        assertEquals("That password is not correct.", AmountPrivacy.revealError(ApiFailure(403, "Password is incorrect")))
        assertTrue(AmountPrivacy.revealError(ApiFailure(429, "Too many attempts")).startsWith("Too many attempts"))
        assertEquals("Cannot reach Apex Books.", AmountPrivacy.revealError(ApiFailure(0, "Cannot reach Apex Books.")))
        assertEquals("Could not check your password. Try again.", AmountPrivacy.revealError(RuntimeException()))
    }
}
