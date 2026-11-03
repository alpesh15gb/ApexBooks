package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApiFailure
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class JournalCommandTest {
    private fun response(body:JSONObject)=JSONObject().put("id","journal-result").put("reference",body.getString("reference").trim()).put("date",body.getString("date"))
    private fun body()=JSONObject().put("date","2026-11-03").put("reference","journal-a").put("memo","Original").put("lines",JSONArray().put(JSONObject().put("account_id","cash").put("debit","100").put("credit","0")))
    @Test fun timeoutRetryKeepsOriginalBodyAndKeyAcrossToolRecreation()=runBlocking{
        val store=ToolDraftStore();val draft=store.get("company-a","journal:create");val sent=mutableListOf<Pair<String,String>>()
        try{submitJournal(draft,body(),true,{true}){value,key->sent.add(value.toString() to key);assertTrue(store.hasUnresolved);throw ApiFailure(0,"Timeout")};fail("Expected timeout")}catch(_:ApiFailure){}
        try{store.remove("company-a","journal:create");fail("Pending journal cannot close")}catch(_:IllegalStateException){}
        val restored=store.get("company-a","journal:create")
        submitJournal(restored,body().put("date","2027-01-01").put("reference","changed"),true,{true}){value,key->sent.add(value.toString() to key);response(value)}
        assertEquals(sent[0],sent[1]);assertFalse(store.hasUnresolved)
    }
    @Test fun reversalReasonAndScopeRemainOriginalAnd409StaysUnknown()=runBlocking{
        val store=ToolDraftStore();val draft=store.get("company-a","reverse_journal:original-a")
        val first=JSONObject().put("date","2026-11-03").put("reference","reverse-a").put("reason","Original reason")
        var frozen=""
        try{submitJournal(draft,first,true,{true}){value,_->frozen=value.toString();throw ApiFailure(409,"Request is in progress")};fail("Expected conflict")}catch(_:ApiFailure){}
        assertTrue(draft.submission.unresolved)
        assertNotSame(draft,store.get("company-a","reverse_journal:original-b"));assertNotSame(draft,store.get("company-b","reverse_journal:original-a"))
        submitJournal(draft,first.put("reason","Changed"),true,{true}){value,_->assertEquals(frozen,value.toString());response(value)}
    }
    @Test fun capabilityAndStaleWorkspaceFailBeforeSubmission()=runBlocking{
        val draft=ToolDraft();var calls=0
        for(available in listOf(false,true))try{submitJournal(draft,body(),available,{false}){value,_->calls++;response(value)};fail("Expected blocked write")}catch(_:IllegalStateException){}
        assertEquals(0,calls);assertFalse(draft.submission.unresolved)
        var current=true
        try{submitJournal(draft,body(),true,{current}){value,_->calls++;current=false;response(value)};fail("Must not update a new workspace")}catch(_:IllegalStateException){}
        assertEquals(1,calls);assertFalse(draft.submission.unresolved)
    }
    @Test fun definitiveValidationAllowsCorrectionButServerFailureRetainsCommand()=runBlocking{
        val draft=ToolDraft()
        try{submitJournal(draft,body(),true,{true}){_,_->throw ApiFailure(422,"Unbalanced")}}catch(_:ApiFailure){}
        assertFalse(draft.submission.unresolved)
        try{submitJournal(draft,body(),true,{true}){_,_->throw ApiFailure(500,"Interrupted")}}catch(_:ApiFailure){}
        assertTrue(draft.submission.unresolved)
    }
    @Test fun exactDefinitiveConflictsUnlockButRetainInputsKeyAndReconciliationWarning()=runBlocking{
        for(message in listOf("Journal retry key was used for a different request","Journal reference already exists","Journal is already reversed or is itself a reversal","Reference already exists or journal was already reversed","Date is in a locked accounting period","Reverse source documents through their document workflow")){
            val draft=ToolDraft();draft.values["reference"]="Retained";val key=draft.key
            try{submitJournal(draft,body(),true,{true}){_,_->throw ApiFailure(0,"Timeout")}}catch(_:ApiFailure){}
            try{submitJournal(draft,body(),true,{true}){_,_->throw ApiFailure(409,message)};fail("Expected rejection")}catch(error:ApiFailure){assertTrue(error.message!!.contains("earlier interrupted attempt may already have saved"))}
            assertTrue(draft.journalReviewRequired)
            try{submitJournal(draft,body(),true,{true}){_,_->fail("Review-required command must not send");JSONObject()};fail("Must require review")}catch(_:IllegalStateException){}
            assertFalse(draft.submission.unresolved);assertEquals("Retained",draft.values["reference"]);assertEquals(key,draft.key)
            assertFalse(definitiveJournalConflict(ApiFailure(409,message+".")));assertFalse(definitiveJournalConflict(ApiFailure(500,message)))
        }
        for(message in listOf("Journal reference already exists","Date is in a locked accounting period")){
            val draft=ToolDraft()
            try{submitJournal(draft,body(),true,{true}){_,_->throw ApiFailure(409,message)}}catch(_:ApiFailure){}
            assertFalse(draft.submission.unresolved)
            submitJournal(draft,body().put("reference","corrected"),true,{true}){value,_->assertEquals("corrected",value.getString("reference"));response(value)}
        }
    }
    @Test fun malformedSuccessAndWrongReversalIdentityStayPending()=runBlocking{
        for(result in listOf(JSONObject(),JSONObject().put("id","journal-result").put("reference","wrong"),response(body()).put("reversal_of","other"))){
            val draft=ToolDraft()
            try{submitJournal(draft,body(),true,{true},originalJournalId="original-a"){_,_->result};fail("Malformed identity must not unlock")}catch(_:IllegalStateException){}
            assertTrue(draft.submission.unresolved)
        }
        val wrongDate=ToolDraft()
        try{submitJournal(wrongDate,body(),true,{true}){value,_->response(value).put("date","2027-01-01")};fail("Wrong date must remain unknown")}catch(_:IllegalStateException){}
        assertTrue(wrongDate.submission.unresolved)
        val bound=ToolDraft()
        try{submitJournal(bound,body(),true,{true}){_,_->throw ApiFailure(409,"Journal retry key was used for a different request")}}catch(_:ApiFailure){}
        assertTrue(bound.journalReviewRequired);assertFalse(bound.submission.unresolved)
        val draft=ToolDraft()
        submitJournal(draft,body(),true,{true},originalJournalId="original-a"){value,_->response(value).put("reversal_of","original-a")}
        assertFalse(draft.submission.unresolved)
    }
}
