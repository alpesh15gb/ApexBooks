package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RetrySubmissionTest {
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
}
