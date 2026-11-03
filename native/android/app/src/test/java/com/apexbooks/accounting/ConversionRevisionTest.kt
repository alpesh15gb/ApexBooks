package com.apexbooks.accounting

import com.apexbooks.accounting.data.RetrySubmission
import com.apexbooks.accounting.data.ApiFailure
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ConversionRevisionTest {
    @Test fun openedSourceRevisionCannotFollowLaterSourceMutation(){
        val source=JSONObject().put("id","draft-original").put("data",JSONObject().put("version",0))
        val opened=ConversionRevision(source)
        source.put("id","different");source.getJSONObject("data").put("version",1)
        val values=JSONObject();opened.applyTo(values)
        assertEquals("draft-original",values.getString("source_document_id"));assertEquals(0L,values.getLong("source_document_version"))
        val retry=RetrySubmission();val original=retry.body(JSONObject().put("data",values))
        values.put("source_document_version",5)
        assertEquals(original.toString(),retry.body(JSONObject().put("data",values)).toString())
    }
    @Test fun legacySourceIsExplicitZeroAndInvalidRevisionsFailClosed(){
        val data=JSONObject();ConversionRevision(JSONObject().put("id","legacy")).applyTo(data)
        assertEquals(0L,data.getLong("source_document_version"))
        for(value in listOf<Any>(-1,"1",1.5,true,JSONObject.NULL)){
            try{ConversionRevision(JSONObject().put("id","draft").put("data",JSONObject().put("version",value)));fail("Invalid revision must fail: $value")}catch(expected:IllegalArgumentException){}
        }
    }
    @Test fun onlyConversionsRequireVerifiedCapability(){
        assertTrue(protectedConversionAllowed(false,emptySet()))
        assertFalse(protectedConversionAllowed(true,emptySet()))
        assertTrue(protectedConversionAllowed(true,setOf("document_conversion_revisions")))
    }
    @Test fun onlyExactConversionRevisionConflictsReleasePendingBody(){
        val messages=listOf("Conversion source revision required; update the app and reopen the source document before converting","Conversion source changed; reopen it and review the conversion again")
        for(message in messages){
            val error=ApiFailure(409,message);val retry=RetrySubmission();retry.body(JSONObject().put("amount","100"))
            retry.failed(error,definitiveConflict=definitiveConversionConflict(true,error));assertFalse(retry.unresolved)
            assertFalse(definitiveConversionConflict(false,error))
            assertFalse(definitiveConversionConflict(true,ApiFailure(500,message)))
        }
        for(message in listOf("Request is still in progress",messages[1]+".","Source already converted")){
            val error=ApiFailure(409,message);val retry=RetrySubmission();retry.body(JSONObject().put("amount","100"))
            retry.failed(error,definitiveConflict=definitiveConversionConflict(true,error));assertTrue(retry.unresolved)
        }
    }
}
