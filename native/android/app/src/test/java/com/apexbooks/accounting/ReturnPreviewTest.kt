package com.apexbooks.accounting

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ReturnPreviewTest {
    @Test fun existingReturnPreviewIncludesSourceAndSelfWithoutMutatingSaveBody(){
        for(kind in listOf("credit_note","debit_note")){
            val body=JSONObject().put("kind",kind).put("data",JSONObject().put("applied_to","source-id"))
            val preview=documentPreviewBody(body,"return-id")
            assertEquals("source-id",preview.getJSONObject("data").getString("applied_to"))
            assertEquals("return-id",preview.getJSONObject("data").getString("preview_record_id"))
            assertFalse(body.getJSONObject("data").has("preview_record_id"))
        }
    }
    @Test fun newReturnAndOtherDocumentPreviewsNeverExcludeAnotherRecord(){
        val body=JSONObject().put("kind","debit_note").put("data",JSONObject().put("applied_to","source-id"))
        assertFalse(documentPreviewBody(body).getJSONObject("data").has("preview_record_id"))
        body.put("kind","purchase_bill")
        assertFalse(documentPreviewBody(body,"bill-id").getJSONObject("data").has("preview_record_id"))
    }
    @Test fun returnLineSeedRetainsSourceIneligibleGstTreatment(){
        val source=JSONObject().put("description","Source goods").put("quantity","3").put("rate","100").put("gst_rate","18").put("itc_treatment","ineligible")
        assertEquals("ineligible",LineState(source,true).json().getString("itc_treatment"))
    }
}
