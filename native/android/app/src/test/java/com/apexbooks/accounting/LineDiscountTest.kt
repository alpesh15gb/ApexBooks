package com.apexbooks.accounting
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LineDiscountTest {
    @Test fun fixedDiscountSurvivesServerPercentZeroAndUnrelatedEdits(){val line=LineState(JSONObject().put("description","Item").put("rate","100").put("quantity","1").put("discount_amount","10").put("discount_percent","0"));assertEquals("amount",line.discountMode);line.set("description","Edited description");assertEquals("10",line.json().getString("discount_amount"));assertFalse(line.json().has("discount_percent"));val reopened=LineState(line.json());assertEquals("10",reopened.json().getString("discount_amount"));assertEquals("amount",LineState(JSONObject().put("discount_amount","0")).discountMode)}
    @Test fun explicitModeSwitchClearsOtherInput(){val line=LineState(JSONObject().put("discount_amount","10"));line.chooseDiscountMode("percent");assertEquals("",line.get("discount_amount"));line.set("discount_percent","5");assertEquals("5",line.json().getString("discount_percent"));assertFalse(line.json().has("discount_amount"));line.chooseDiscountMode("amount");assertEquals("",line.get("discount_percent"));assertEquals("0",line.json().getString("discount_amount"));assertFalse(line.json().has("discount_percent"))}
    @Test fun quantityChangesNeverProrateFixedDiscountAndInvalidateReview(){val line=LineState(JSONObject().put("quantity","2").put("discount_amount","10").put("price_includes_tax",true).put("gst_rate","18"));val before=line.discountRevision;line.set("quantity","1");assertEquals("10",line.json().getString("discount_amount"));assertTrue(line.discountRevision>before);line.set("quantity","2");assertTrue(line.discountRevision>before+1);assertTrue(line.json().getBoolean("price_includes_tax"))}
    @Test fun selectedReturnSourceReplacesIdentityAndSurvivesQuantityEditsAndReopen(){
        val first=JSONObject().put("description","Same service").put("source_line_id","0:first").put("source_document_id","bill").put("source_line_number",1).put("quantity","2").put("itc_treatment","ineligible")
        val second=JSONObject(first.toString()).put("source_line_id","1:second").put("source_line_number",2).put("itc_treatment","pending_review").put("discount_amount","5")
        val line=LineState(first);val identity=line.uiKey;line.selectSource(second);line.set("quantity","1")
        assertEquals(identity,line.uiKey);assertEquals("1:second",line.json().getString("source_line_id"));assertEquals("bill",line.json().getString("source_document_id"));assertEquals("pending_review",line.get("itc_treatment"));assertEquals("amount",line.discountMode)
        val reopened=LineState(line.json());assertEquals("1:second",reopened.get("source_line_id"));assertEquals("1",reopened.get("quantity"))
    }
}
