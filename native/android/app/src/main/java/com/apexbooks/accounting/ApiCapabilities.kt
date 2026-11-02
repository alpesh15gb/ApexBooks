package com.apexbooks.accounting

import org.json.JSONObject

/** Fail closed for additive workflows; legacy accounting remains usable. */
data class CapabilityResult(val features:Set<String> = emptySet(),val retryable:Boolean=false)
object ApiCapabilities {
    val masterFields=mapOf("is_active" to "master_lifecycle","shipping_address" to "party_shipping_address","credit_limit" to "party_credit_limits","payment_terms_days" to "party_payment_terms","low_stock_threshold" to "low_stock_reorder")
    suspend fun fetchResult(request:suspend ()->JSONObject):CapabilityResult = try{CapabilityResult(parse(request()))}catch(e:Exception){if(e is kotlinx.coroutines.CancellationException)throw e;CapabilityResult(retryable=e !is com.apexbooks.accounting.data.ApiFailure||e.status!=404)}
    suspend fun fetch(request:suspend ()->JSONObject):Set<String> = fetchResult(request).features
    fun parse(value:JSONObject):Set<String> {
        if(value.optInt("capabilities_version")!=1)return emptySet()
        val features=value.optJSONArray("supported_features")?:return emptySet()
        return (0 until features.length()).mapNotNull{features.opt(it) as? String}.toSet()
    }
    fun unsupportedChanges(initial:Map<String,String>,current:Map<String,String>,supported:Set<String>)=masterFields.filter{(field,feature)->feature !in supported&&initial[field].orEmpty()!=current[field].orEmpty()}.keys
    fun filterMaster(values:JSONObject,supported:Set<String>){masterFields.forEach{(field,feature)->if(feature !in supported)values.remove(field)}}
}

fun companyDisplayName(company:JSONObject):String {val name=company.optString("name","");val label=company.optString("book_label","").takeUnless{it=="null"}.orEmpty().trim();return if(label.isBlank())name else "$name · $label"}
fun companySearchText(company:JSONObject)=companyDisplayName(company)

@androidx.compose.runtime.Composable fun FeatureUpgradeHint(vm:AppModel){androidx.compose.material3.Text(vm.capabilityHint,style=androidx.compose.material3.MaterialTheme.typography.bodySmall);if(vm.capabilityRetryable)androidx.compose.material3.TextButton(enabled=!vm.capabilityChecking,onClick={vm.retryCapabilities()}){androidx.compose.material3.Text("Retry feature check")}}
