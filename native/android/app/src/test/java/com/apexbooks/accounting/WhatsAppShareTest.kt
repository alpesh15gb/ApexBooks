package com.apexbooks.accounting

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

class WhatsAppShareTest {
    @Test fun sharingUsesLinkedIdentityAndRetainsDocumentPhoneFallback() {
        val row=JSONObject("""{"name":"Same name","data":{"party_id":"linked","party_phone":"9000000003"}}""")
        val other=JSONObject("""{"kind":"party","id":"other","name":"Same name","data":{"phone":"9000000001"}}""")
        val linked=JSONObject("""{"kind":"party","id":"linked","name":"Renamed party","data":{"phone":"9000000002"}}""")
        assertEquals("9000000002",WhatsAppShare.partyPhone(row,listOf(other,linked)))
        assertEquals("9000000003",WhatsAppShare.partyPhone(row,listOf(other)))
        linked.getJSONObject("data").put("phone","")
        assertEquals("9000000003",WhatsAppShare.partyPhone(row,listOf(other,linked)))
        row.getJSONObject("data").remove("party_id")
        assertEquals("9000000001",WhatsAppShare.partyPhone(row,listOf(other)))
        assertEquals("9000000003",WhatsAppShare.partyPhone(row,emptyList()))
    }
}
