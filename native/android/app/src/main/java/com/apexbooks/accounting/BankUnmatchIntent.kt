package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApiFailure
import org.json.JSONObject

/** One reviewed exact-match identity. Retries never adopt a subsequently loaded match. */
class BankUnmatchIntent(val companyId:String,val workspaceStamp:Int,line:JSONObject){
    val lineId=line.optString("id").also{require(it.isNotBlank()){ "Reload the statement before unmatching." }}
    private val recordId=line.optString("matched_record_id").also{require(it.isNotBlank()&&it!="null"){ "There is no reviewed exact match to remove. Reload the statement." }}
    private val revision:Long=line.opt("match_revision").let{value->
        require((value is Int||value is Long)&&(value as Number).toLong()>=0){"The statement has no valid match revision. Reload it after updating the server; nothing was submitted."}
        (value as Number).toLong()
    }
    init{require(companyId.isNotBlank())}
    fun body()=JSONObject().put("expected_record_id",recordId).put("expected_match_revision",revision)
    suspend fun execute(supported:Boolean,current:()->Boolean,send:suspend(String,String,JSONObject)->Unit){
        check(supported){"Exact unmatching requires verified bank match revision support. Nothing was submitted."}
        check(current()){ "The original company or session changed. Reload its statement before unmatching." }
        try{send(companyId,lineId,body())}catch(error:ApiFailure){
            if(error.status==409&&error.message in setOf("Bank match revision required; update the app and reload the statement before unmatching","Bank match changed; reload the statement and review its current match"))
                throw ApiFailure(409,"${error.message}. An earlier interrupted unmatch may have succeeded. Review the current match before taking another action.")
            throw error
        }
        check(current()){ "The unmatch completed in the original company. Reload that statement to review the result." }
    }
}
