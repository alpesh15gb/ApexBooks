package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONObject

fun inlineMasterAllowed(kind:String,editing:Boolean,converting:Boolean,canWrite:Boolean)=kind=="sales_invoice"&&!editing&&!converting&&canWrite
fun pristineInlinePlaceholder(line:LineState,regular:Boolean)=line.discountMode=="percent"&&line.values.toMap()==LineState(regular=regular).values.toMap()
fun canAppendInlineItem(lines:List<LineState>,regular:Boolean)=lines.size<100||(lines.size==1&&pristineInlinePlaceholder(lines.single(),regular))
fun appendInlineItem(lines:MutableList<LineState>,item:JSONObject,regular:Boolean){
    require(item.s("kind")=="item"&&item.s("id").isNotBlank()){"The server did not return a saved item identity."}
    require(canAppendInlineItem(lines,regular)){"The invoice already has 100 lines. Remove a line before creating an item."}
    val newLine=LineState(regular=regular);newLine.linkProduct(item,false,regular)
    if(lines.size==1&&pristineInlinePlaceholder(lines.single(),regular))lines[0]=newLine else lines.add(newLine)
}
fun inlineDuplicateConflict(error:Exception)=error is ApiFailure&&error.status==409&&error.message=="A party or item with this name already exists"

fun inlineMasterResponseMatches(created:JSONObject,body:JSONObject,companyId:String)=created.s("id").isNotBlank()&&created.opt("data") is JSONObject&&(!created.o("data").has("is_active")||created.o("data").opt("is_active") is Boolean)&&created.s("kind")==body.s("kind")&&created.s("name")==body.s("name").trim()&&(created.s("company_id").isBlank()||created.s("company_id")==companyId)

fun appendCreatedMasterToCatalogue(rows:List<JSONObject>,created:JSONObject):List<JSONObject>{
    require(created.s("kind") in setOf("party","item")&&created.s("id").isNotBlank())
    return if(rows.any{it.s("id")==created.s("id")})rows else rows+created
}
