package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApiFailure
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ToolDraftStoreTest {
    @Test fun restoredToolRetainsInputsOriginalRequestAndKey(){
        val store=ToolDraftStore();val first=store.get("company-a","settle:advance-a")
        first.values["amount"]="100";first.submission.body(JSONObject(first.values.toMap()));first.submission.failed(ApiFailure(0,"timeout"))
        val restored=store.get("company-a","settle:advance-a")
        assertSame(first,restored);assertEquals(first.key,restored.key);assertEquals("100",restored.values["amount"])
        restored.values["amount"]="999";assertEquals("100",restored.submission.body(JSONObject(restored.values.toMap())).getString("amount"));assertTrue(store.hasUnresolved)
        try{store.remove("company-a","settle:advance-a");fail("Unresolved draft must remain recoverable")}catch(_:IllegalStateException){}
        restored.submission.succeeded();store.remove("company-a","settle:advance-a");assertFalse(store.hasUnresolved)
    }
    @Test fun companyAndCommandScopesNeverShareDrafts(){
        val store=ToolDraftStore();val first=store.get("company-a","stock")
        first.values["quantity"]="5"
        assertTrue(store.get("company-b","stock").values.isEmpty());assertTrue(store.get("company-a","other").values.isEmpty())
        store.clear();assertTrue(store.get("company-a","stock").values.isEmpty())
    }
}
