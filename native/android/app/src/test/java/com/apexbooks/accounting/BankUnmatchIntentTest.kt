package com.apexbooks.accounting

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class BankUnmatchIntentTest {
    private fun row()=JSONObject().put("id","line-a").put("matched_record_id","record-a").put("match_revision",0)
    @Test fun capturesExactMatchAndDoesNotAdoptReplacement(){
        val line=row();val intent=BankUnmatchIntent("company-a",12,line)
        line.put("id","line-b").put("matched_record_id","record-b").put("match_revision",3)
        assertEquals("line-a",intent.lineId);assertEquals("record-a",intent.body().getString("expected_record_id"));assertEquals(0L,intent.body().getLong("expected_match_revision"))
        intent.body().put("expected_match_revision",99)
        assertEquals(0L,intent.body().getLong("expected_match_revision"))
    }
    @Test fun revisionMustBeExplicitNonnegativeInteger(){
        val missing=row().apply{remove("match_revision")}
        val invalid=listOf(missing)+listOf<Any>(JSONObject.NULL,-1,"0",0.5,true).map{row().put("match_revision",it)}
        invalid.forEach{try{BankUnmatchIntent("company-a",1,it);fail("Missing/malformed revision must reject")}catch(expected:IllegalArgumentException){}}
    }
    @Test fun unsupportedAndStaleWorkspaceNeverSend()=runBlocking{
        val intent=BankUnmatchIntent("company-a",12,row());var calls=0
        for(supported in listOf(false,true))try{intent.execute(supported,{false}){_,_,_->calls++};fail("Must reject")}catch(expected:IllegalStateException){}
        assertEquals(0,calls)
        var current=true
        try{intent.execute(true,{current}){company,line,body->assertEquals("company-a",company);assertEquals("line-a",line);assertEquals("record-a",body.getString("expected_record_id"));calls++;current=false};fail("Late completion must not update another workspace")}catch(expected:IllegalStateException){}
        assertEquals(1,calls)
    }
    @Test fun unknownOutcomeRetryRetainsOriginalPairAndOnlyKnownConflictsAddGuidance()=runBlocking{
        val line=row();val intent=BankUnmatchIntent("company-a",12,line);val bodies=mutableListOf<String>()
        try{intent.execute(true,{true}){_,_,body->bodies.add(body.toString());throw com.apexbooks.accounting.data.ApiFailure(0,"Timeout")};fail("Expected unknown outcome")}catch(error:com.apexbooks.accounting.data.ApiFailure){assertEquals(0,error.status)}
        line.put("matched_record_id","replacement").put("match_revision",2)
        intent.execute(true,{true}){_,_,body->bodies.add(body.toString())}
        assertEquals(bodies[0],bodies[1])
        val unrelated=com.apexbooks.accounting.data.ApiFailure(409,"In progress")
        try{intent.execute(true,{true}){_,_,_->throw unrelated};fail("Expected conflict")}catch(error:com.apexbooks.accounting.data.ApiFailure){assertSame(unrelated,error)}
        try{intent.execute(true,{true}){_,_,_->throw com.apexbooks.accounting.data.ApiFailure(409,"Bank match changed; reload the statement and review its current match")};fail("Expected stale match")}catch(error:com.apexbooks.accounting.data.ApiFailure){assertTrue(error.message!!.contains("earlier interrupted unmatch"))}
    }
}
