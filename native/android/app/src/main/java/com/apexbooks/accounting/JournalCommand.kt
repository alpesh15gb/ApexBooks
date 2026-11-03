package com.apexbooks.accounting

import org.json.JSONObject
import com.apexbooks.accounting.data.ApiFailure

/** Session-only command state supplied by the ViewModel-owned tool draft. */
suspend fun submitJournal(draft:ToolDraft,candidate:JSONObject,supported:Boolean,current:()->Boolean,originalJournalId:String?=null,send:suspend(JSONObject,String)->JSONObject){
    check(supported){"Journal posting requires verified retry protection. Nothing was submitted."}
    check(current()){ "The original company or session changed. Reopen its journal tool." }
    check(!draft.journalReviewRequired){"Close and review journal history before starting a new command."}
    val wasUnknown=draft.submission.unresolved
    val body=draft.submission.body(candidate)
    try{
        val result=send(body,draft.key)
        check(result.optString("id").isNotBlank()&&result.optString("id")!="null"&&result.optString("reference")==body.optString("reference").trim()&&(if(originalJournalId==null)result.optString("date")==body.optString("date") else result.optString("reversal_of")==originalJournalId)){"The journal response could not be verified. Retry the original save before creating another."}
    }catch(error:Exception){
        val rejected=definitiveJournalConflict(error)
        draft.submission.failed(error,definitiveConflict=rejected)
        if(rejected&&(wasUnknown||error.message=="Journal retry key was used for a different request"))draft.journalReviewRequired=true
        if(rejected)throw ApiFailure(409,"${error.message}. Your entered values remain here. An earlier interrupted attempt may already have saved. Close and review the journal history before correcting or posting again.")
        throw error
    }
    draft.submission.succeeded()
    check(current()){ "The journal saved in the original company. Refresh that company to review it." }
}

fun definitiveJournalConflict(error:Exception)=error is ApiFailure&&error.status==409&&error.message in setOf(
    "Journal retry key was used for a different request",
    "Journal reference already exists",
    "Journal is already reversed or is itself a reversal",
    "Reference already exists or journal was already reversed",
    "Date is in a locked accounting period",
    "Reverse source documents through their document workflow"
)
