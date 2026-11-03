package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class InlineMasterFlowTest {
    private fun item()=JSONObject().put("id","created-item").put("kind","item").put("name","New service").put("data",JSONObject().put("item_type","services").put("track_stock",false).put("sale_rate","25").put("unit","hour").put("gst_rate","18"))
    @Test fun onlyNewWritableSalesInvoicesOfferInlineCreation(){
        assertTrue(inlineMasterAllowed("sales_invoice",false,false,true))
        assertFalse(inlineMasterAllowed("sales_invoice",true,false,true));assertFalse(inlineMasterAllowed("sales_invoice",false,true,true));assertFalse(inlineMasterAllowed("sales_invoice",false,false,false));assertFalse(inlineMasterAllowed("purchase_bill",false,false,true))
    }
    @Test fun exactPristinePlaceholderMayBeReused(){
        val lines=mutableListOf(LineState(regular=true));appendInlineItem(lines,item(),true)
        assertEquals(1,lines.size);assertEquals("created-item",lines.single().get("item_id"));assertEquals("25",lines.single().get("rate"));assertEquals("1",lines.single().get("quantity"))
    }
    @Test fun editedQuantityFixedDiscountAndTaxBasisAreNeverOverwritten(){
        val existing=LineState(JSONObject().put("description","Original").put("quantity","3").put("rate","100").put("discount_amount","10").put("price_includes_tax",true),true)
        val before=existing.json().toString();val lines=mutableListOf(existing);appendInlineItem(lines,item(),true)
        assertSame(existing,lines[0]);assertEquals(before,existing.json().toString());assertEquals(2,lines.size)
        val customBlank=LineState(regular=true).also{it.set("quantity","2")};assertFalse(pristineInlinePlaceholder(customBlank,true))
        val explicitZeroFixed=LineState(regular=true).also{it.chooseDiscountMode("amount");it.set("discount_amount","0")};assertFalse(pristineInlinePlaceholder(explicitZeroFixed,true))
    }
    @Test fun itemCreationCannotExceedHundredLines(){
        val lines=MutableList(100){LineState(regular=true)};assertFalse(canAppendInlineItem(lines,true))
        assertThrows(IllegalArgumentException::class.java){appendInlineItem(lines,item(),true)};assertEquals(100,lines.size)
    }
    @Test fun exactDuplicateRejectionDoesNotTreatOtherConflictsAsResolved(){
        assertTrue(inlineDuplicateConflict(ApiFailure(409,"A party or item with this name already exists")))
        assertFalse(inlineDuplicateConflict(ApiFailure(409,"Request in progress")))
        val state=RetrySubmission();val original=JSONObject().put("kind","party").put("name","Created customer").put("date","2026-11-03")
        state.body(original);state.failed(ApiFailure(0,"timeout"));assertTrue(state.unresolved)
        val retry=state.body(JSONObject().put("name","Changed").put("date","2026-11-04"));assertEquals("Created customer",retry.getString("name"));assertEquals("2026-11-03",retry.getString("date"))
    }
    @Test fun onlyMatchingReturnedIdentityMayUnlockCreation(){
        val body=JSONObject().put("kind","item").put("name","New service")
        assertTrue(inlineMasterResponseMatches(item(),body,"company"))
        assertFalse(inlineMasterResponseMatches(item().put("id",""),body,"company"))
        val missingData=item();missingData.remove("data");assertFalse(inlineMasterResponseMatches(missingData,body,"company"))
        assertFalse(inlineMasterResponseMatches(item().put("kind","party"),body,"company"))
        assertFalse(inlineMasterResponseMatches(item().put("name","Existing other master"),body,"company"))
        assertFalse(inlineMasterResponseMatches(item().put("company_id","other"),body,"company"))
        for(value in listOf<Any>("true",1,JSONObject.NULL)){val malformed=item();malformed.getJSONObject("data").put("is_active",value);assertFalse(inlineMasterResponseMatches(malformed,body,"company"))}
        val inactive=item();inactive.getJSONObject("data").put("is_active",false)
        assertTrue("An archived identity is a known creation outcome, not an unknown request",inlineMasterResponseMatches(inactive,body,"company"))
        assertFalse(selectableMaster(inactive))
    }

    @Test fun catalogueAppendPreservesExistingNewerMasterAndFinancialRows(){
        val invoice=JSONObject().put("id","invoice").put("kind","sales_invoice")
        val newer=item().put("name","Latest saved name");val rows=listOf(invoice,newer)
        assertSame(rows,appendCreatedMasterToCatalogue(rows,item()))
        val other=item().put("id","second-item");val added=appendCreatedMasterToCatalogue(rows,other)
        assertEquals(3,added.size);assertSame(invoice,added[0]);assertSame(newer,added[1]);assertSame(other,added[2])
        assertThrows(IllegalArgumentException::class.java){appendCreatedMasterToCatalogue(rows,invoice)}
    }

}
