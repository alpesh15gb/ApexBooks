package com.apexbooks.accounting.data

import org.json.JSONArray
import org.json.JSONObject

/** Strict only for company lists, bank lists and complete record scans; never silently drop rows. */
fun companyRows(value:Any?,label:String,maximum:Int?=null):List<JSONObject>{
    val array=value as? JSONArray?:throw ApiFailure(502,"Invalid $label response. Refresh and try again; no incomplete company data was loaded.")
    if(maximum!=null&&array.length()>maximum)throw ApiFailure(502,"Invalid $label page size. Refresh and try again; no incomplete company data was loaded.")
    return (0 until array.length()).map{index->
        val row=array.opt(index) as? JSONObject
        val id=row?.opt("id")
        if(row==null||id !is String||id.isBlank())throw ApiFailure(502,"Invalid $label row. Refresh and try again; no incomplete company data was loaded.")
        row
    }
}

suspend fun collectCompanyRecords(fetch:suspend(Int)->Any?):List<JSONObject>{
    // Offset pages are not a snapshot. Preserve the existing single restart on overlap.
    repeat(2){
        val rows=mutableListOf<JSONObject>();val seen=hashSetOf<String>();var offset=0
        while(true){
            val page=companyRows(fetch(offset),"company records",500)
            if(page.any{!seen.add(it.getString("id"))})break
            rows.addAll(page)
            if(page.size<500)return rows
            offset+=500
        }
    }
    throw ApiFailure(409,"Company records changed while loading. No incomplete history was loaded. Refresh and try again.")
}
