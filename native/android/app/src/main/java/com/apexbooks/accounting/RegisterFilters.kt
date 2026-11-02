package com.apexbooks.accounting

import org.json.JSONObject
import com.apexbooks.accounting.data.*

fun shippingForPartySelection(current:String,lastDefault:String,suggested:String)=if(current.isBlank()||current==lastDefault)suggested else current

fun partyShippingAddress(party:JSONObject)=party.o("data").s("shipping_address").ifBlank{party.o("data").s("address")}

fun selectableMaster(row:JSONObject,retainedId:String="")=row.o("data").optBoolean("is_active",true)||(retainedId.isNotBlank()&&row.s("id")==retainedId)

fun registerStatus(row:JSONObject):String {
    if(row.s("kind") in setOf("party","item"))return if(row.o("data").optBoolean("is_active",true))"Active"else"Inactive"
    if(row.s("converted_to").isNotBlank())return "Converted"
    if(row.optBoolean("posted")){
        if(row.o("data").optBoolean("is_advance"))return if(row.decimal("advance_remaining").signum()>0)"Advance available"else"Advance settled"
        if(row.s("kind") in setOf("credit_note","debit_note"))return if(row.decimal("credit_remaining").signum()>0)"Credit available"else"Credit settled"
        if(row.s("kind") in setOf("sales_invoice","purchase_bill","pos")&&row.has("outstanding")&&!row.isNull("outstanding")){
            val due=row.s("outstanding").toBigDecimalOrNull()?:return "Posted"
            val amount=row.s("amount").toBigDecimalOrNull()?:return "Posted"
            return if(due.signum()<=0)"Settled"else if(due<amount)"Part settled"else"Unpaid"
        }
        return "Posted"
    }
    return if(row.s("kind") in setOf("estimate","proforma","sales_order","purchase_order"))"Draft"else""
}

fun filterRegister(records:List<JSONObject>,kind:String,query:String,start:String,end:String,party:String,status:String,sort:String):List<JSONObject>{
    val master=kind in setOf("party","item")
    val matches=records.filter{r->val data=r.o("data");r.s("kind")==kind&&(!master||status=="all"||registerStatus(r)==status)&&(r.s("name")+" "+r.s("number")+" "+data.s("phone")+" "+data.s("barcode")+" "+data.s("hsn")).contains(query.trim(),true)&&(master||((start.isBlank()||r.s("date")>=start)&&(end.isBlank()||r.s("date")<=end)&&(party=="all"||r.s("name")==party)&&(status=="all"||registerStatus(r)==status)))}
    return when(sort){"old"->matches.sortedWith(compareBy<JSONObject>{it.s("date")}.thenBy{it.o("data").s("created_at")}.thenBy{it.s("number")});"name"->matches.sortedBy{it.s("name").lowercase()};"amount"->matches.sortedByDescending{it.s("amount").toBigDecimalOrNull()?:java.math.BigDecimal.ZERO};else->matches.sortedWith(compareByDescending<JSONObject>{it.s("date")}.thenByDescending{it.o("data").s("created_at")}.thenByDescending{it.s("id")})}
}
