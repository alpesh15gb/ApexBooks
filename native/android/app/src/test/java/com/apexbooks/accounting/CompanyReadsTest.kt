package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CompanyReadsTest {
    private fun page(start:Int,count:Int)=JSONArray().also{array->repeat(count){array.put(JSONObject().put("id","row-${start+it}"))}}
    private fun reject(value:Any?,maximum:Int?=500){try{companyRows(value,"company records",maximum);fail("Malformed response accepted")}catch(_:ApiFailure){}}
    @Test fun malformedEnvelopeRowsAndIdentityFailClosed(){
        for(value in listOf(null,JSONObject.NULL,JSONObject(),"[]",true,42))reject(value)
        for(value in listOf(JSONObject.NULL,JSONArray(),"row",true,42,JSONObject(),JSONObject().put("id",42),JSONObject().put("id",true),JSONObject().put("id",JSONObject.NULL),JSONObject().put("id",""),JSONObject().put("id"," \t")))reject(JSONArray().put(value))
        reject(page(0,501))
    }
    @Test fun companyAndBankListsKeepExactIdsAndFutureFields(){
        val row=JSONObject().put("id"," default ").put("new_future_field",JSONObject().put("value",true))
        for(label in listOf("companies","bank accounts")){
            val loaded=companyRows(JSONArray().put(row),label)
            assertSame(row,loaded.single());assertEquals(" default ",loaded.single().getString("id"))
            assertTrue(loaded.single().getJSONObject("new_future_field").getBoolean("value"))
        }
        assertEquals("default",companyRows(JSONArray().put(JSONObject().put("id","default")),"bank accounts").single().getString("id"))
        assertTrue(companyRows(JSONArray(),"companies").isEmpty())
    }
    @Test fun malformedFirstOrLaterPageNeverReturnsPartialRows()=runBlocking{
        val invalid=listOf<Any>(JSONObject().put("detail","temporary error"),JSONArray().put(JSONObject().put("id",0)),page(0,499).put(JSONObject.NULL),page(0,501))
        for(bad in invalid)for(later in listOf(false,true)){
            var calls=0;var published=listOf(JSONObject().put("id","previous-confirmed"))
            try{published=collectCompanyRecords{offset->calls++;if(later&&offset==0)page(0,500)else bad};fail("Malformed page accepted")}catch(_:ApiFailure){}
            assertEquals("previous-confirmed",published.single().getString("id"));assertEquals(if(later)2 else 1,calls)
        }
    }
    @Test fun validPagingAndSingleOverlapRestartKeepExistingSemantics()=runBlocking{
        val offsets=mutableListOf<Int>()
        val rows=collectCompanyRecords{offset->offsets.add(offset);if(offset==0)page(0,500)else page(500,1)}
        assertEquals(501,rows.size);assertEquals(listOf(0,500),offsets)
        var calls=0;offsets.clear()
        val restarted=collectCompanyRecords{offset->offsets.add(offset);calls++;when(calls){1->page(0,500);2->page(499,1);3->page(0,500);else->page(500,1)}}
        assertEquals(501,restarted.size);assertEquals(listOf(0,500,0,500),offsets)
        calls=0
        try{collectCompanyRecords{calls++;JSONArray().put(JSONObject().put("id","same")).put(JSONObject().put("id","same"))};fail("Repeated overlap accepted")}catch(e:ApiFailure){assertEquals(409,e.status)}
        assertEquals(2,calls)
    }
    @Test fun pageFailureDoesNotReturnEarlierValidRows()=runBlocking{
        var published=listOf(JSONObject().put("id","confirmed"))
        try{published=collectCompanyRecords{offset->if(offset==0)page(0,500)else throw ApiFailure(0,"Synthetic timeout")};fail("Expected timeout")}catch(_:ApiFailure){}
        assertEquals("confirmed",published.single().getString("id"))
    }
}
