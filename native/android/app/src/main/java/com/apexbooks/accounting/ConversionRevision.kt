package com.apexbooks.accounting

import org.json.JSONObject

/** The reviewed source identity/version; never refreshed while its editor is open. */
class ConversionRevision(source:JSONObject){
    private val id=source.getString("id").also{require(it.isNotBlank()){ "The source draft identity is missing. Close and reload it." }}
    private val version:Long=source.optJSONObject("data")?.let{data->
        if(!data.has("version"))0L else {
            val value=data.opt("version")
            require((value is Int||value is Long)&&(value as Number).toLong()>=0){"The source draft revision is invalid. Close and reload it."}
            (value as Number).toLong()
        }
    }?:0L
    fun applyTo(data:JSONObject){data.put("source_document_id",id).put("source_document_version",version)}
}
fun protectedConversionAllowed(converting:Boolean,supported:Set<String>) = !converting || "document_conversion_revisions" in supported

fun definitiveConversionConflict(converting:Boolean,error:Exception):Boolean = converting &&
    error is com.apexbooks.accounting.data.ApiFailure && error.status==409 && error.message in setOf(
        "Conversion source revision required; update the app and reopen the source document before converting",
        "Conversion source changed; reopen it and review the conversion again"
    )
