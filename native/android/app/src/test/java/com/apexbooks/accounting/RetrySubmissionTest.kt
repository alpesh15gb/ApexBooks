package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RetrySubmissionTest {
    @Test fun unknownOutcomesRemainNonDiscardableUntilRecovered() {
        for(status in listOf(0,408,409,500,502,503,504)) {
            val submission=RetrySubmission()
            submission.body(JSONObject().put("amount","100"))
            submission.failed(ApiFailure(status,"unknown outcome"))
            assertTrue("Must block dismissal for $status",submission.unresolved)
            assertEquals("100",submission.body(JSONObject().put("amount","999")).getString("amount"))
            submission.succeeded()
            assertFalse(submission.unresolved)
        }
    }

    @Test fun uncertainWritePreservesOriginalPayloadDespiteEdits() {
        val submission=RetrySubmission()
        val original=JSONObject().put("amount","100").put("data",JSONObject().put("quantity","1"))
        val sent=submission.body(original)
        original.put("amount","200")
        sent.getJSONObject("data").put("quantity","99")
        submission.failed(ApiFailure(0,"timeout"))
        assertTrue(submission.unresolved)
        val retry=submission.body(original)
        assertEquals("100",retry.getString("amount"))
        assertEquals("1",retry.getJSONObject("data").getString("quantity"))
    }
    @Test fun definitiveValidationAllowsCorrectionButServerFailureDoesNot() {
        val submission=RetrySubmission()
        submission.body(JSONObject().put("amount","bad"))
        submission.failed(ApiFailure(422,"invalid"))
        assertFalse(submission.unresolved)
        assertEquals("20",submission.body(JSONObject().put("amount","20")).getString("amount"))
        submission.failed(ApiFailure(500,"unknown"))
        assertTrue(submission.unresolved)
        submission.succeeded()
        assertFalse(submission.unresolved)
    }
    @Test fun definitiveMasterRevisionConflictAllowsReconciliationWithoutRebasingDraft() {
        val draft=JSONObject().put("name","My entered name").put("version",0)
        val submission=RetrySubmission();submission.body(draft)
        submission.failed(ApiFailure(0,"interrupted response"))
        assertTrue(submission.unresolved)
        submission.failed(ApiFailure(409,"stale master revision"),definitiveConflict=true)
        assertFalse(submission.unresolved)
        assertEquals("My entered name",draft.getString("name"))
        assertEquals(0,draft.getInt("version"))
        assertEquals(0,submission.body(draft).getInt("version"))
    }
    @Test fun masterServerFailureStillPreservesOriginalVersionAndPayload() {
        val submission=RetrySubmission();submission.body(JSONObject().put("name","Original draft").put("version",4))
        submission.failed(ApiFailure(503,"unknown"),definitiveConflict=true)
        assertTrue(submission.unresolved)
        val retry=submission.body(JSONObject().put("name","Changed draft").put("version",5))
        assertEquals(4,retry.getInt("version"));assertEquals("Original draft",retry.getString("name"))
    }

}
