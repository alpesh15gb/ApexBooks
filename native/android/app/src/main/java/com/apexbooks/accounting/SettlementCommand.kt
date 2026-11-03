package com.apexbooks.accounting

import androidx.compose.runtime.*
import com.apexbooks.accounting.data.RetrySubmission
import org.json.JSONObject

/** In-memory only. The complete route/body survives recomposition and unknown outcomes. */
class SettlementCommand(private val submission:RetrySubmission,private val key:String) {
    var sending by mutableStateOf(false);private set
    private var company:String?=null
    private var workspace:Int?=null
    suspend fun submit(cid:String,stamp:Int,current:()->Boolean,candidate:()->JSONObject,send:suspend(String,JSONObject,String)->JSONObject){
        check(!sending){"The original settlement is still being submitted."}
        check(current()&&(company==null||company==cid&&workspace==stamp)){"The original company or session changed. Return to its pending settlement before continuing."}
        val wasUnknown=submission.unresolved
        sending=true
        try{
            // Do not consult a refreshed source catalogue when recovering an existing command.
            val command=if(submission.unresolved)submission.body(JSONObject())else{
                val prepared=candidate();company=cid;workspace=stamp;submission.body(prepared)
            }
            val body=command.getJSONObject("body")
            try{
                val result=send(command.getString("path"),body,key)
                val data=result.optJSONObject("data")?:JSONObject()
                val expectedAmount=body.getString("amount").trim().toBigDecimalOrNull()
                val returnedAmount=result.optString("amount").trim().toBigDecimalOrNull()
                val requested=body.getJSONObject("data")
                val refund=requested.getString("action")=="refund"
                check((!command.has("payment_kind")||data.optString("payment_kind")==command.getString("payment_kind"))&&
                    (!refund||(data.optString("payment_account")==requested.getString("payment_account")&&data.optString("bank_account_id")==requested.optString("bank_account_id").ifBlank{"default"}))&&
                    result.opt("posted")==true&&result.opt("id") is String&&result.getString("id").isNotBlank()&&result.getString("id")!="null"&&
                    result.optString("kind")==command.getString("result_kind")&&result.optString("date")==body.getString("date")&&
                    expectedAmount!=null&&returnedAmount!=null&&returnedAmount.compareTo(expectedAmount)==0&&
                    data.optString(command.getString("source_field"))==command.getString("source_id")&&
                    (body.getJSONObject("data").getString("action")!="apply"||data.optString("applied_to")==body.getJSONObject("data").getString("applied_to"))){
                    "The settlement response could not be verified. Retry the original save before creating another."
                }
            }catch(error:Exception){
                // Auth/validation rejection on a retry cannot disprove an earlier commit.
                if(!wasUnknown)submission.failed(error)
                throw error
            }
            submission.succeeded();company=null;workspace=null
            check(current()){ "The settlement saved in the original company. Refresh that company to review it." }
        }finally{sending=false}
    }
}

fun settlementCandidate(cid:String,tool:String,values:JSONObject,source:JSONObject):JSONObject {
    require(tool in setOf("settle_credit","settle_advance"))
    val credit=tool=="settle_credit";val id=values.getString("source");val action=values.getString("action")
    require(id.isNotBlank()&&source.getString("id")==id&&action in setOf("apply","refund"))
    val data=JSONObject().put("action",action).put("applied_to",values.optString("target")).put("payment_account",values.optString("method")).put("bank_account_id",values.optString("bank_account_id"))
    val body=JSONObject().put("kind","advance_application").put("name",source.getString("name")).put("date",values.getString("date")).put("amount",values.getString("amount")).put("data",data)
    val resultKind=if(!credit){if(action=="apply")"advance_application"else"advance_refund"}else if(action=="apply")"credit_application"else if(source.getString("kind")=="credit_note")"customer_refund"else"supplier_refund"
    val command=JSONObject().put("path",if(credit)"/api/companies/$cid/credits/$id/settle"else"/api/companies/$cid/advances/$id/$action")
        .put("body",body).put("result_kind",resultKind).put("source_field",if(credit)"credit_note_id"else"advance_id").put("source_id",id)
    if(!credit||action=="apply")command.put("payment_kind",if(credit){if(source.getString("kind")=="credit_note")"payment_in"else"payment_out"}else source.getString("kind"))
    return command
}
