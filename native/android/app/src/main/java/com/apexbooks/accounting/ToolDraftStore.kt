package com.apexbooks.accounting

import androidx.compose.runtime.mutableStateMapOf
import com.apexbooks.accounting.data.RetrySubmission
import java.util.UUID

/** Session-only financial tool drafts. AppModel ownership survives activity recreation. */
class ToolDraft {
    val key=UUID.randomUUID().toString()
    val submission=RetrySubmission()
    val values=mutableStateMapOf<String,String>()
}
class ToolDraftStore {
    private val drafts=mutableMapOf<Pair<String,String>,ToolDraft>()
    fun get(company:String,scope:String)=drafts.getOrPut(company to scope){ToolDraft()}
    val hasUnresolved get()=drafts.values.any{it.submission.unresolved}
    fun remove(company:String,scope:String){check(drafts[company to scope]?.submission?.unresolved!=true){"Recover the original save before discarding this tool draft."};drafts.remove(company to scope)}
    fun clear(){drafts.clear()}
}
