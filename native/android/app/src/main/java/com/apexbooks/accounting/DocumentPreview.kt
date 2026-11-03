package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONObject

/** Preview context only: never mutate the body retained for an actual save. */
fun documentPreviewBody(body:JSONObject,previousId:String=""):JSONObject=copy(body).also{preview->
    val data=preview.o("data")
    data.remove("preview_record_id")
    if(preview.s("kind") in setOf("credit_note","debit_note")&&previousId.isNotBlank())data.put("preview_record_id",previousId)
    preview.put("data",data)
}
