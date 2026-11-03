package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RecordEditRetryTest {
    private fun body(amount:String="150")=JSONObject().put("kind","expense").put("amount",amount).put("data",JSONObject().put("version",0).put("notes","Original change"))
    @Test fun timeoutThenRejectedReplayRetainsOriginalEditUntilSuccess(){
        for(status in listOf(401,403,404,408,409,422,500)){
            val submission=RetrySubmission();val original=submission.body(body()).toString()
            recordEditWriteFailed(submission,ApiFailure(0,"Lost response"),true,false)
            val wasUnknown=submission.unresolved
            val retried=submission.body(body("999"))
            recordEditWriteFailed(submission,ApiFailure(status,"Retry rejected"),true,wasUnknown)
            assertTrue("Prior edit remains unknown after $status",submission.unresolved)
            assertEquals(original,retried.toString());assertEquals(original,submission.body(body("300")).toString())
            // A successful old-key replay may return the CURRENT record at a later amount/version.
            // No original amount/version equality is imposed by this failure policy.
            submission.succeeded();assertFalse(submission.unresolved)
        }
    }
    @Test fun freshDefinitiveRejectionsStillPermitCorrection(){
        for(status in listOf(401,403,404,422)){
            val submission=RetrySubmission();val wasUnknown=submission.unresolved;submission.body(body())
            recordEditWriteFailed(submission,ApiFailure(status,"Not committed"),true,wasUnknown)
            assertFalse(submission.unresolved);assertEquals("175",submission.body(body("175")).getString("amount"))
        }
    }
    @Test fun freshGenericConflictRemainsUnknown(){
        val submission=RetrySubmission();submission.body(body())
        recordEditWriteFailed(submission,ApiFailure(409,"Conflict"),true,false)
        assertTrue(submission.unresolved)
    }
    @Test fun masterReconciliationAndNonEditPoliciesAreUnchanged(){
        val master=RetrySubmission();master.body(body())
        recordEditWriteFailed(master,ApiFailure(409,"Master revision conflict"),false,true,true)
        assertFalse(master.unresolved)
        val creation=RetrySubmission();creation.body(body())
        recordEditWriteFailed(creation,ApiFailure(422,"Validation"),false,true)
        assertFalse(creation.unresolved)
    }
}
