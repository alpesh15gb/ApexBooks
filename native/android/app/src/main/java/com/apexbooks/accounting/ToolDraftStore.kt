package com.apexbooks.accounting

import androidx.compose.runtime.*
import com.apexbooks.accounting.data.RetrySubmission
import java.util.UUID

/** Session-only financial tool drafts. AppModel ownership survives activity recreation. */
class ToolDraft {
    var journalReviewRequired by mutableStateOf(false)
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
