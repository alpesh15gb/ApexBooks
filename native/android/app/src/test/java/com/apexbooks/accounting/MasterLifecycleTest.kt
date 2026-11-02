package com.apexbooks.accounting

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MasterLifecycleTest {
    private fun master(id:String,active:Boolean?=null)=JSONObject().put("id",id).put("kind","item").put("name",id).put("data",JSONObject().apply{if(active!=null)put("is_active",active)})
    @Test fun shippingUsesSavedDestinationOrBillingFallback(){val party=JSONObject().put("data",JSONObject().put("address","Billing road").put("shipping_address","Delivery road"));assertEquals("Delivery road",partyShippingAddress(party));party.getJSONObject("data").put("shipping_address","");assertEquals("Billing road",partyShippingAddress(party))}
    @Test fun changingPartyPreservesManualShippingOverride(){assertEquals("New default",shippingForPartySelection("Old default","Old default","New default"));assertEquals("Manual destination",shippingForPartySelection("Manual destination","Old default","New default"));assertEquals("New default",shippingForPartySelection("","","New default"))}
    @Test fun missingActivityFlagIsLegacyActive(){assertTrue(selectableMaster(master("legacy")));assertEquals("Active",registerStatus(master("legacy")))}
    @Test fun inactiveOnlySelectableAsExactRetainedHistoricalIdentity(){
        val inactive=master("archived",false)
        assertFalse(selectableMaster(inactive));assertFalse(selectableMaster(inactive,"different"));assertTrue(selectableMaster(inactive,"archived"))
    }
    @Test fun inactiveMastersRemainSearchableAndFilterable(){
        val rows=listOf(master("active",true),master("archived",false))
        assertEquals(2,filterRegister(rows,"item","","","","all","all","name").size)
        assertEquals("archived",filterRegister(rows,"item","","","","all","Inactive","name").single().getString("id"))
    }
}
