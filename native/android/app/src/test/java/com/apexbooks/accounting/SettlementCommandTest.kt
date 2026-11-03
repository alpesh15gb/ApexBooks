package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApiFailure
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SettlementCommandTest {
    private fun values()=JSONObject().put("source","source-a").put("action","apply").put("target","invoice-a").put("method","cash").put("bank_account_id","default").put("date","2026-11-03").put("amount","100")
    private fun source()=JSONObject().put("id","source-a").put("name","Original party").put("kind","credit_note").put("credit_remaining","100")
    private fun result(body:JSONObject)=JSONObject().put("posted",true).put("id","posted-result").put("kind","credit_application").put("date",body.getString("date")).put("amount",body.getString("amount")).put("data",JSONObject().put("payment_kind","payment_in").put("credit_note_id","source-a").put("applied_to","invoice-a"))
    @Test fun refreshedZeroBalanceAndRenamedSourceDoNotRebuildUnknownCommand()=runBlocking{
        val store=ToolDraftStore();val draft=store.get("company-a","settle_credit")
        val row=source();val entered=values();var candidates=0;val calls=mutableListOf<Triple<String,String,String>>()
        fun candidate():JSONObject{candidates++;check(row.getString("credit_remaining")!="0");return settlementCandidate("company-a","settle_credit",entered,row)}
        try{draft.settlement.submit("company-a",1,{true},::candidate){path,body,key->calls.add(Triple(path,body.toString(),key));throw ApiFailure(0,"Timeout")};fail("Expected timeout")}catch(_:ApiFailure){}
        assertTrue(store.hasUnresolved)
        try{store.remove("company-a","settle_credit");fail("Cannot discard unknown settlement")}catch(_:IllegalStateException){}
        row.put("credit_remaining","0").put("name","Changed party");entered.put("source","other").put("action","refund").put("amount","900")
        store.get("company-a","settle_credit").settlement.submit("company-a",1,{true},::candidate){path,body,key->calls.add(Triple(path,body.toString(),key));result(body)}
        assertEquals(1,candidates);assertEquals(calls[0],calls[1]);assertFalse(store.hasUnresolved)
    }
    @Test fun workspaceReplacementBlocksRetryAndLateCompletionCannotTouchNewWorkspace()=runBlocking{
        val draft=ToolDraft();var current=true;var sends=0
        val candidate={settlementCandidate("company-a","settle_credit",values(),source())}
        try{draft.settlement.submit("company-a",1,{current},candidate){_,_,_->sends++;throw ApiFailure(500,"Unknown")}}catch(_:ApiFailure){}
        for((company,stamp) in listOf("company-b" to 1,"company-a" to 2))try{draft.settlement.submit(company,stamp,{true},candidate){_,body,_->sends++;result(body)};fail("Wrong workspace")}catch(_:IllegalStateException){}
        assertEquals(1,sends);assertTrue(draft.submission.unresolved)
        // Explicit current callback controls stale completion notification, independent of identity args.
        val other=ToolDraft();current=true
        try{other.settlement.submit("company-a",1,{current},candidate){_,body,_->current=false;result(body)};fail("Late completion must not close a replacement tool")}catch(_:IllegalStateException){}
        assertFalse(other.submission.unresolved)
    }
    @Test fun concurrentClickDoesNotSendTwice()=runBlocking{
        val draft=ToolDraft();val started=CompletableDeferred<Unit>();val release=CompletableDeferred<Unit>();var sends=0
        val candidate={settlementCandidate("company-a","settle_credit",values(),source())}
        val first=launch{draft.settlement.submit("company-a",1,{true},candidate){_,body,_->sends++;started.complete(Unit);release.await();result(body)}}
        started.await();assertTrue(draft.settlement.sending)
        try{draft.settlement.submit("company-a",1,{true},candidate){_,body,_->sends++;result(body)};fail("Concurrent click must be blocked")}catch(_:IllegalStateException){}
        assertEquals(1,sends);release.complete(Unit);first.join();assertFalse(draft.settlement.sending)
    }
    @Test fun malformedSuccessAndGeneric409RetainOriginalCommandBut422AllowsCorrection()=runBlocking{
        for(amount in listOf(".5"," +.5 ","0.5000")){
            val normal=ToolDraft()
            normal.settlement.submit("company-a",1,{true},{settlementCandidate("company-a","settle_credit",values().put("amount",amount),source())}){_,body,_->result(body).put("amount","0.50")}
            assertFalse(normal.submission.unresolved)
        }
        val draft=ToolDraft();val entered=values();var candidates=0
        val candidate={candidates++;settlementCandidate("company-a","settle_credit",entered,source())}
        try{draft.settlement.submit("company-a",1,{true},candidate){_,_,_->JSONObject()};fail("Malformed success")}catch(_:IllegalStateException){}
        assertTrue(draft.submission.unresolved)
        try{draft.settlement.submit("company-a",1,{true},candidate){_,_,_->throw ApiFailure(409,"Unknown conflict")}}catch(_:ApiFailure){}
        assertTrue(draft.submission.unresolved);assertEquals(1,candidates)
        for(status in listOf(403,422)){
            try{draft.settlement.submit("company-a",1,{true},candidate){_,_,_->throw ApiFailure(status,"Rejected retry")}}catch(_:ApiFailure){}
            assertTrue(draft.submission.unresolved);assertEquals(1,candidates)
        }
        val fresh=ToolDraft()
        try{fresh.settlement.submit("company-a",1,{true},candidate){_,_,_->throw ApiFailure(422,"Invalid amount")}}catch(_:ApiFailure){}
        assertFalse(fresh.submission.unresolved)
        entered.put("amount","50");fresh.settlement.submit("company-a",1,{true},candidate){_,body,_->assertEquals("50",body.getString("amount"));result(body)}
        assertEquals(3,candidates)
    }
    @Test fun timeoutThenAuthorizationOrValidationRejectionCannotDiscardPriorOutcome()=runBlocking{
        for(status in listOf(403,422)){
            val store=ToolDraftStore();val draft=store.get("company-a","settle_credit")
            val candidate={settlementCandidate("company-a","settle_credit",values(),source())}
            try{draft.settlement.submit("company-a",1,{true},candidate){_,_,_->throw ApiFailure(0,"Timeout")}}catch(_:ApiFailure){}
            try{draft.settlement.submit("company-a",1,{true},candidate){_,_,_->throw ApiFailure(status,"Denied retry")}}catch(_:ApiFailure){}
            assertTrue(store.hasUnresolved)
            try{store.remove("company-a","settle_credit");fail("Earlier outcome still unknown")}catch(_:IllegalStateException){}
        }
    }
    @Test fun wrongResponseIdentityAmountDateAndTargetStayUnknown()=runBlocking{
        for(field in listOf("id","kind","date","amount","source","target","posted_false","posted_missing","posted_string","payment_kind")){
            val draft=ToolDraft()
            try{draft.settlement.submit("company-a",1,{true},{settlementCandidate("company-a","settle_credit",values(),source())}){_,body,_->
                result(body).also{reply->when(field){
                    "payment_kind"->reply.getJSONObject("data").put("payment_kind","payment_out")
                    "posted_false"->reply.put("posted",false)
                    "posted_missing"->reply.remove("posted")
                    "posted_string"->reply.put("posted","true")
                    "id"->reply.put("id",JSONObject.NULL)
                    "source"->reply.getJSONObject("data").put("credit_note_id","different")
                    "target"->reply.getJSONObject("data").put("applied_to","different")
                    else->reply.put(field,"different")
                }}
            };fail("Wrong $field should remain unknown")}catch(_:IllegalStateException){}
            assertTrue(draft.submission.unresolved)
        }
    }
    @Test fun refundAcknowledgementMustMatchOriginalAccountAndAdvanceSide()=runBlocking{
        for(tool in listOf("settle_credit","settle_advance"))for(corrupt in listOf("none","method","bank","side")){
            if(tool=="settle_credit"&&corrupt=="side")continue // Credit refunds do not return payment_kind.
            val draft=ToolDraft();val row=source().put("kind",if(tool=="settle_credit")"credit_note"else"payment_out")
            val entered=values().put("action","refund").put("method","bank").put("bank_account_id","bank-a")
            val command=settlementCandidate("company-a",tool,entered,row)
            try{draft.settlement.submit("company-a",1,{true},{command}){_,body,_->
                val data=JSONObject().put(command.getString("source_field"),"source-a").put("payment_account","bank").put("bank_account_id","bank-a")
                if(command.has("payment_kind"))data.put("payment_kind",command.getString("payment_kind"))
                when(corrupt){"method"->data.put("payment_account","cash");"bank"->data.put("bank_account_id","other");"side"->data.put("payment_kind","payment_in")}
                JSONObject().put("posted",true).put("id","refund-id").put("kind",command.getString("result_kind")).put("date",body.getString("date")).put("amount",body.getString("amount")).put("data",data)
            };assertEquals("none",corrupt)}catch(_:IllegalStateException){assertNotEquals("none",corrupt)}
            assertEquals(corrupt!="none",draft.submission.unresolved)
        }
    }
    @Test fun allSettlementRoutesAndExpectedResultKindsAreCaptured(){
        for(tool in listOf("settle_credit","settle_advance"))for(action in listOf("apply","refund")){
            val row=source().put("kind",if(tool=="settle_credit")"debit_note"else"payment_out")
            val command=settlementCandidate("company-a",tool,values().put("action",action),row)
            assertEquals(if(tool=="settle_credit")"/api/companies/company-a/credits/source-a/settle"else"/api/companies/company-a/advances/source-a/$action",command.getString("path"))
            assertEquals(if(tool=="settle_credit"){if(action=="apply")"credit_application"else"supplier_refund"}else{if(action=="apply")"advance_application"else"advance_refund"},command.getString("result_kind"))
        }
    }
}
