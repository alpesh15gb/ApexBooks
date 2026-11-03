package com.apexbooks.accounting

import com.apexbooks.accounting.data.businessDate
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class ApiCapabilitiesTest {
    @Test fun buildIdentityIsExplicitAndValidated() {assertEquals("unknown",ApiCapabilities.revision(""));assertEquals("unknown",ApiCapabilities.revision("a".repeat(40)+"\n"));assertEquals("a".repeat(40),ApiCapabilities.revision("A".repeat(40)));assertEquals("b".repeat(64),ApiCapabilities.revision("b".repeat(64)));assertEquals("1.5.0",ApiCapabilities.version("1.5.0"));assertEquals("unknown",ApiCapabilities.version("null"))}

    @Test fun transientFailureOffersRetryInsteadOfUpgrade()=kotlinx.coroutines.runBlocking {assertFalse(ApiCapabilities.fetchResult{throw com.apexbooks.accounting.data.ApiFailure(404,"old API")}.retryable);assertTrue(ApiCapabilities.fetchResult{throw com.apexbooks.accounting.data.ApiFailure(0,"timeout")}.retryable);assertTrue(ApiCapabilities.fetchResult{throw com.apexbooks.accounting.data.ApiFailure(503,"temporarily unavailable")}.retryable);val recovered=ApiCapabilities.fetchResult{JSONObject("""{"capabilities_version":1,"supported_features":["party_payment_terms"]}""")};assertFalse(recovered.retryable);assertTrue("party_payment_terms" in recovered.features)}
    @Test fun legacy404AndNetworkFailureDisableOnlyAdditiveFeatures()=kotlinx.coroutines.runBlocking {for(status in listOf(404,0,503)){val features=ApiCapabilities.fetch{throw com.apexbooks.accounting.data.ApiFailure(status,"unavailable")};assertTrue(features.isEmpty());val core=JSONObject().put("name","Edited legacy party").put("is_active",true).put("payment_terms_days",JSONObject.NULL);ApiCapabilities.filterMaster(core,features);assertEquals("Edited legacy party",core.getString("name"));assertFalse(core.has("payment_terms_days"));assertFalse("No book-label input permitted without capability", "company_book_labels" in features)}}
    @Test fun unsupportedUserEditsAreRejectedNotReportedSaved(){val original=mapOf("name" to "Old", "is_active" to "true", "payment_terms_days" to "");assertTrue(ApiCapabilities.unsupportedChanges(original,original+mapOf("name" to "Edited"),emptySet()).isEmpty());assertEquals(setOf("payment_terms_days","low_stock_threshold"),ApiCapabilities.unsupportedChanges(original,original+mapOf("payment_terms_days" to "30","low_stock_threshold" to "5"),emptySet()));assertTrue(ApiCapabilities.unsupportedChanges(original,original+mapOf("payment_terms_days" to "30"),setOf("party_payment_terms")).isEmpty())}
    @Test fun bookLabelsDoNotReplaceLegalIdentity(){val company=JSONObject().put("name","Legal Co").put("book_label","FY 2026");assertEquals("Legal Co · FY 2026",companyDisplayName(company));assertEquals("Legal Co",company.getString("name"));assertEquals("Legal Co",companyDisplayName(JSONObject().put("name","Legal Co")))}
    @Test fun unknownContractAndMissingFlagsFailClosed(){assertTrue(ApiCapabilities.parse(JSONObject()).isEmpty());assertTrue(ApiCapabilities.parse(JSONObject("""{"capabilities_version":2,"supported_features":["master_lifecycle"]}""")).isEmpty());assertEquals(setOf("master_lifecycle"),ApiCapabilities.parse(JSONObject("""{"capabilities_version":1,"supported_features":["master_lifecycle",23]}""")))}
    @Test fun legacyMasterPayloadOmitsUnsupportedAdditiveMetadata(){val value=JSONObject().put("name","Party").put("address","Billing");ApiCapabilities.masterFields.keys.forEach{value.put(it,"value")};ApiCapabilities.filterMaster(value,setOf("party_payment_terms"));assertEquals("Party",value.getString("name"));assertEquals("Billing",value.getString("address"));assertTrue(value.has("payment_terms_days"));assertFalse(value.has("is_active"));assertFalse(value.has("shipping_address"));assertFalse(value.has("credit_limit"));assertFalse(value.has("low_stock_threshold"))}
    @Test fun sharedDatesUseIndiaBoundaryNotHostTimezone(){assertEquals("2026-11-02",businessDate(Instant.parse("2026-11-02T18:29:59Z")).toString());assertEquals("2026-11-03",businessDate(Instant.parse("2026-11-02T18:30:00Z")).toString())}
    @Test fun existingMasterEditsRequireVerifiedRevisionCapability(){
        assertFalse(protectedMasterEditAllowed(true,emptySet()))
        assertFalse(protectedMasterEditAllowed(true,setOf("master_lifecycle")))
        assertTrue(protectedMasterEditAllowed(true,setOf("master_edit_revisions")))
        assertTrue(protectedMasterEditAllowed(false,emptySet()))
    }

}
