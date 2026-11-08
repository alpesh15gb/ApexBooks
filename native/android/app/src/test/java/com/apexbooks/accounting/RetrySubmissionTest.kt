package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RetrySubmissionTest {
    @Test fun documentAndPaymentRetryAsOneImmutableCommand() {
        val submission=RetrySubmission()
        val payment=JSONObject().put("amount","40").put("payment_account","bank").put("bank_account_id","bank-a")
        val first=submission.recordCommand({JSONObject().put("amount","100")},{payment})
        payment.put("amount","90").put("bank_account_id","bank-b")
        first.getJSONObject("record").put("amount","999")
        submission.failed(ApiFailure(0,"response lost"))
        val retry=submission.recordCommand({error("Must not re-read document")},{error("Must not re-read payment toggle or amount")})
        assertEquals("100",retry.getJSONObject("record").getString("amount"))
        assertEquals("40",retry.getJSONObject("payment").getString("amount"))
        assertEquals("bank-a",retry.getJSONObject("payment").getString("bank_account_id"))
        submission.failed(ApiFailure(422,"rejected"))
        assertNull(submission.recordCommand({JSONObject().put("amount","200")},{null}).optJSONObject("payment"))
    }

    @Test fun invalidLocalPaymentDoesNotFreezeTheDocument() {
        val submission=RetrySubmission()
        try {
            submission.recordCommand({JSONObject().put("name","Before correction")},{throw IllegalArgumentException("Enter payment amount")})
            fail("Expected local validation")
        } catch (_: IllegalArgumentException) { }
        assertFalse(submission.unresolved)
        val corrected=submission.recordCommand({JSONObject().put("name","Corrected")},{JSONObject().put("amount","50")})
        assertEquals("Corrected",corrected.getJSONObject("record").getString("name"))
    }

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
}
