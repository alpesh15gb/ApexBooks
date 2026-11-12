package com.apexbooks.accounting

import androidx.compose.runtime.*
import com.apexbooks.accounting.data.*
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal

class LineState(initial:JSONObject=JSONObject(),regular:Boolean=false,val importedFromOcr:Boolean=false) {
    val originalItemId=initial.s("item_id")
    // Lazy-list keys must be supported by Android Bundle state restoration.
    val uiKey:String=java.util.UUID.randomUUID().toString()
    val values=mutableStateMapOf<String,String>()
    var discountMode by mutableStateOf(if(initial.has("discount_amount")&&!initial.isNull("discount_amount"))"amount" else "percent");private set
    var discountRevision by mutableIntStateOf(0);private set
    var returnCapacity by mutableStateOf(initial.s("remaining_return_quantity"));private set
    var returnCapacityReason by mutableStateOf(initial.s("return_capacity_reason"));private set
    init { for(key in listOf("source_line_id","source_document_id","source_line_number","description","item_id","quantity","rate","hsn","unit","mrp","discount_percent","discount_amount","gst_rate","tax_treatment","itc_treatment"))values[key]=initial.s(key)
        if(get("quantity").isBlank())values["quantity"]="1";if(get("rate").isBlank())values["rate"]="0";if(get("gst_rate").isBlank())values["gst_rate"]=if(regular)"18" else "0";if(get("tax_treatment").isBlank())values["tax_treatment"]="taxable";if(get("itc_treatment").isBlank())values["itc_treatment"]="pending_review";values["price_includes_tax"]=initial.optBoolean("price_includes_tax").toString() }
    fun get(key:String)=values[key]?:""
    fun set(key:String,value:String){if(key in setOf("quantity","discount_amount","discount_percent")&&get(key)!=value)discountRevision++;values[key]=value}
    fun selectSource(source:JSONObject){val selected=LineState(source);values.clear();values.putAll(selected.values);discountMode=selected.discountMode;returnCapacity=source.s("remaining_return_quantity");returnCapacityReason=source.s("return_capacity_reason");set("quantity",additionalReturnQuantity(source.s("return_capacity_scope"),returnCapacity));discountRevision++}
    fun chooseDiscountMode(mode:String){require(mode in setOf("percent","amount"));if(mode!=discountMode){discountMode=mode;values["discount_percent"]="";values["discount_amount"]="";discountRevision++}}
    fun linkProduct(item:JSONObject,purchase:Boolean,regular:Boolean){
        val data=item.o("data");set("item_id",item.s("id"));set("description",item.s("name"))
        for(key in listOf("hsn","unit"))if(!importedFromOcr||data.s(key).isNotBlank())set(key,data.s(key))
        // Mapping stock identity must not silently reprice an extracted supplier bill.
        if(importedFromOcr)return
        set("rate",data.s(if(purchase)"purchase_rate" else "sale_rate"));set("gst_rate",if(regular||purchase)data.s("gst_rate")else"0")
        var type=data.s("tax_treatment").ifBlank{"taxable"};if(regular&&!purchase&&data.decimal("gst_rate").signum()==0&&type=="taxable")type="nil_rated";set("tax_treatment",type)
    }
    fun json():JSONObject=JSONObject().also{result->values.forEach{(key,value)->if(key !in setOf("discount_percent","discount_amount")||key==if(discountMode=="amount")"discount_amount" else "discount_percent")result.put(key,if(key=="price_includes_tax")value=="true" else if(key in setOf("discount_percent","discount_amount","mrp")&&value.isBlank())"0" else value)}}
}
fun purchaseReturnChoices(rows:List<JSONObject>,line:LineState):List<Pair<String,String>> {
    val selected=line.get("source_line_id")
    val choices=rows.filter{it.s("source_line_id").isNotBlank()}.map{it.s("source_line_id") to "Line ${it.s("source_line_number")} · ${it.s("description")} · source qty ${it.s("quantity")} · additional return qty ${it.s("remaining_return_quantity").ifBlank{"needs review"}} · GST ${it.s("gst_rate")}% · ${it.s("itc_treatment")}"}
    val saved=if(selected.isNotBlank()&&choices.none{it.first==selected})listOf(selected to "Saved source line ${line.get("source_line_number")}")else emptyList()
    return (if(selected.isBlank())listOf("" to "Choose source line or match item/description")else emptyList())+saved+choices
}
class AllocationState(id:String="",amount:String="") { var documentId by mutableStateOf(id);var amount by mutableStateOf(amount) }

class EntryEditor(val vm:AppModel,val kind:String,val previous:JSONObject?=null,val conversion:JSONObject?=null) {
    val companyId=vm.companyId;val workspaceStamp=vm.workspaceStamp();val regular=vm.regular
    val fields=mutableStateMapOf<String,String>()
    val lines=mutableStateListOf<LineState>()
    val allocations=mutableStateListOf<AllocationState>()
    val originalAllocations:List<JSONObject>
    val purchase=kind in setOf("purchase_bill","purchase_order","debit_note","expense")
    val document=kind in vm.documentKinds;val payment=kind in setOf("payment_in","payment_out");val master=kind in setOf("party","item")
    var saving by mutableStateOf(false);var scanning by mutableStateOf(false);var sourceLoading by mutableStateOf(false)
    var preview by mutableStateOf<JSONObject?>(null);var previewError by mutableStateOf("");var ocrTotal by mutableStateOf("")
    private var returnEditRevision by mutableIntStateOf(0)
    private var reviewedReturnSignature by mutableStateOf("")
    val hasFixedLinkedReturn get()=kind in setOf("credit_note","debit_note")&&get("applied_to").isNotBlank()&&lines.any{it.discountMode=="amount"&&(it.get("discount_amount").toBigDecimalOrNull()?:BigDecimal.ZERO).signum()>0}
    private val returnSignature get()=get("applied_to")+":"+returnEditRevision+":"+lines.joinToString("|"){it.uiKey+":"+it.discountRevision}
    val fixedReturnReviewNeeded get()=hasFixedLinkedReturn&&reviewedReturnSignature!=returnSignature
    fun acknowledgeReturnDiscount(checked:Boolean){reviewedReturnSignature=if(checked)returnSignature else ""}
    private var sourceSequence=0
    var requestedSource by mutableStateOf<String?>(null);private set
    var retryKey=vm.key();private set
    private var initialSignature=""
    private var initialMasterFields:Map<String,String> = emptyMap()
    val submission=RetrySubmission()
    var retryPending by mutableStateOf(false);private set
    val canEdit get()=!saving&&!scanning&&!sourceLoading&&!retryPending&&quickAdding.isBlank()
    val canSaveAndNew get()=document&&previous==null&&conversion==null
    val canPayNow get()=previous==null&&conversion==null&&kind in setOf("sales_invoice","purchase_bill")&&vm.supports("payment_at_entry")
    fun paymentBody():JSONObject?{
        if(!canPayNow||!flag("pay_now"))return null
        val paid=get("pay_amount").toBigDecimalOrNull()
        if(paid==null||paid.signum()<=0)throw Exception(if(kind=="sales_invoice")"Enter the amount received, or switch off Received now." else "Enter the amount paid, or switch off Paid now.")
        val total=preview?.s("amount")?.toBigDecimalOrNull()
        if(total!=null&&paid>total)throw Exception("The amount cannot be more than the document total.")
        return JSONObject().put("amount",paid.setScale(2,java.math.RoundingMode.HALF_UP).toPlainString()).put("payment_account",get("pay_account").ifBlank{"cash"}).put("bank_account_id",if(get("pay_account")=="bank")get("pay_bank").ifBlank{"default"}else"default")
    }
    fun changed()=if(master)fields.toMap()!=initialMasterFields else body().toString()!=initialSignature||flag("pay_now")
    fun renewRetryKey(){retryKey=vm.key();submission.succeeded();retryPending=false}
    init {
        val source=previous?:conversion?:JSONObject();val data=source.o("data")
        for(key in listOf("credit_limit","payment_terms_days","low_stock_threshold","party_id","party_address","party_gstin","party_phone","shipping_address","place_of_supply","supplier_state","due_date","notes","terms","category","payment_account","bank_account_id","applied_to","advance_supply","advance_gst_rate","document_discount_percent","tender_amount","gstin","address","phone","email","party_type","hsn","unit","sale_rate","purchase_rate","gst_rate","barcode","item_type","tax_treatment","image_data_url","image_thumbnail"))fields[key]=data.s(key)
        fields["name"]=source.s("name");fields["number"]=previous?.s("number")?:"";fields["date"]=previous?.s("date")?:today();fields["amount"]=previous?.s("amount")?:""
        if(purchase&&get("supplier_state").isBlank())fields["supplier_state"]=supplierOrigin(data)
        for((key,value)in mapOf("place_of_supply" to vm.company.s("state_code"),"supplier_state" to vm.company.s("state_code"),"payment_account" to "cash","bank_account_id" to "default","advance_supply" to "goods","advance_gst_rate" to "18","document_discount_percent" to "0","category" to "General","party_type" to "both","item_type" to "goods","tax_treatment" to "taxable","sale_rate" to "0","purchase_rate" to "0","gst_rate" to "0"))if(get(key).isBlank())fields[key]=value
        fields["is_active"]=data.optBoolean("is_active",true).toString();for(key in listOf("is_advance","round_total","track_stock"))fields[key]=data.optBoolean(key).toString();fields["return_stock"]=data.optBoolean("return_stock",true).toString()
        data.a("lines").objects().forEach{lines.add(LineState(it,regular))};if(document&&lines.isEmpty())lines.add(LineState(regular=regular))
        originalAllocations=(previous?.a("allocations")?.objects()?.takeIf{it.isNotEmpty()}?:data.a("allocations").objects()).ifEmpty{if(data.s("applied_to").isNotBlank())listOf(JSONObject().put("document_id",data.s("applied_to")).put("amount",source.s("amount")))else emptyList()}
        originalAllocations.forEach{allocations.add(AllocationState(it.s("document_id"),it.s("amount")))};if(payment&&allocations.isEmpty())allocations.add(AllocationState())
        initialMasterFields=fields.toMap();initialSignature=body().toString();if(previous!=null)reviewedReturnSignature=returnSignature
    }
    private fun supplierOrigin(data:JSONObject)=data.s("supplier_state").ifBlank{data.s("party_gstin").take(2).takeIf{it.length==2&&it.all{c->c.isDigit()}}?:vm.company.s("state_code")}
    fun get(key:String)=fields[key]?:""
    fun set(key:String,value:String){if(key in setOf("applied_to","document_discount_percent")&&get(key)!=value)returnEditRevision++;fields[key]=value}
    fun flag(key:String)=get(key)=="true"
    private var lastPartyShipping=""
    fun parties()=vm.records.filter{it.s("kind")=="party"&&selectableMaster(it,previous?.o("data")?.s("party_id")?:"")}
    fun items(line:LineState)=vm.records.filter{it.s("kind")=="item"&&selectableMaster(it,if(previous!=null)line.originalItemId else "")}
    fun chooseParty(id:String){if(id.isBlank()){set("party_id","");return};val party=parties().find{it.s("id")==id}?:return;set("name",party.s("name"));set("party_id",id);val data=party.o("data");set("party_address",data.s("address"));set("party_phone",data.s("phone"));set("party_gstin",data.s("gstin"));val shipping=partyShippingAddress(party);fields["shipping_address"]=shippingForPartySelection(get("shipping_address"),lastPartyShipping,shipping);lastPartyShipping=shipping;set(if(purchase)"supplier_state" else "place_of_supply",data.s("gstin").take(2).ifBlank{vm.company.s("state_code")})}
    fun changePartyName(value:String){if(!value.trim().equals(get("name").trim(),true)){for(key in listOf("party_id","party_address","party_gstin","party_phone"))set(key,"");if(get("shipping_address")==lastPartyShipping)fields["shipping_address"]="";lastPartyShipping="";set("place_of_supply",vm.company.s("state_code"));set("supplier_state",vm.company.s("state_code"))};set("name",value)}
    fun chooseItem(line:LineState,id:String){val item=items(line).find{it.s("id")==id}?:return;line.linkProduct(item,purchase,regular)}
    // Quick-add (Vyapar / MyBillBook style): save the typed customer or line as a master without leaving the document.
    var quickAdding by mutableStateOf("");private set
    val canQuickAdd get()=document&&kind !in setOf("credit_note","debit_note","expense")&&vm.company.s("role") in setOf("owner","editor")
    private suspend fun createMaster(masterKind:String,name:String,data:JSONObject):JSONObject=
        vm.api.request(vm.api.company(companyId,"/records"),"POST",JSONObject().put("kind",masterKind).put("name",name.trim()).put("date",today()).put("amount","0").put("data",data)) as JSONObject
    fun quickAddParty(){
        val name=get("name").trim();if(name.isBlank()||get("party_id").isNotBlank()||quickAdding.isNotBlank())return
        quickAdding="party"
        vm.task{try{
            val created=createMaster("party",name,JSONObject().put("party_type",if(purchase)"supplier" else "customer").put("phone",get("party_phone").trim()).put("gstin",get("party_gstin").trim().uppercase()).put("address",get("party_address")).put("shipping_address",get("shipping_address")))
            if(!vm.inWorkspace(companyId,workspaceStamp))return@task
            vm.rememberMaster(created);fields["name"]=created.s("name");fields["party_id"]=created.s("id");vm.notice="Saved ${created.s("name")} as a new ${if(purchase)"supplier" else "customer"}."
        }finally{quickAdding=""}}
    }
    fun quickAddItem(line:LineState){
        val name=line.get("description").trim();if(name.isBlank()||line.get("item_id").isNotBlank()||quickAdding.isNotBlank())return
        quickAdding=line.uiKey
        vm.task{try{
            fun amount(value:String)=(value.toBigDecimalOrNull()?:BigDecimal.ZERO).setScale(2,java.math.RoundingMode.HALF_UP).toPlainString()
            val created=createMaster("item",name,JSONObject().put("item_type","goods").put("hsn",line.get("hsn")).put("unit",line.get("unit")).put(if(purchase)"purchase_rate" else "sale_rate",amount(line.get("rate"))).put("gst_rate",amount(line.get("gst_rate"))).put("tax_treatment",line.get("tax_treatment").ifBlank{"taxable"}))
            if(!vm.inWorkspace(companyId,workspaceStamp))return@task
            vm.rememberMaster(created);line.set("item_id",created.s("id"));line.set("description",created.s("name"));vm.notice="Saved ${created.s("name")} as a new item."
        }finally{quickAdding=""}}
    }
    fun targets():List<JSONObject> = vm.records.filter{r->r.optBoolean("posted")&&when(kind){"payment_in"->r.s("kind")in setOf("sales_invoice","opening_receivable");"payment_out"->r.s("kind")in setOf("purchase_bill","opening_payable");"credit_note"->r.s("kind")in setOf("sales_invoice","pos");"debit_note"->r.s("kind")=="purchase_bill";else->false}&&(!payment||available(r)>BigDecimal.ZERO||originalAllocations.any{it.s("document_id")==r.s("id")})}
    fun available(row:JSONObject)=row.decimal("outstanding")+originalAllocations.filter{it.s("document_id")==row.s("id")}.fold(BigDecimal.ZERO){sum,a->sum+a.decimal("amount")}
    fun chooseAllocation(row:AllocationState,index:Int,id:String) {
        row.documentId=id
        val target=targets().find{it.s("id")==id}?:run{row.amount="";return}
        if(index==0){
            val changed=!target.s("name").trim().equals(get("name").trim(),true)
            changePartyName(target.s("name"))
            if(changed)allocations.removeAll{it!==row}
        }
        val available=available(target).max(BigDecimal.ZERO)
        if(get("amount").isBlank())set("amount",available.toPlainString())
        val others=allocations.filter{it!==row}.fold(BigDecimal.ZERO){sum,it->sum+(it.amount.toBigDecimalOrNull()?:BigDecimal.ZERO)}
        val remaining=((get("amount").toBigDecimalOrNull()?:BigDecimal.ZERO)-others).max(BigDecimal.ZERO)
        row.amount=available.min(remaining).toPlainString()
    }
    val returnSourceLines=mutableStateListOf<JSONObject>()
    fun setReturnSourceLines(source:JSONObject){returnSourceLines.clear();returnSourceLines.addAll(source.a("return_capacity_lines").objects().ifEmpty{source.o("data").a("lines").objects()})}
    fun chooseReturnLine(line:LineState,id:String){
        val source=returnSourceLines.find{it.s("source_line_id")==id}?:return
        if(lines.contains(line))line.selectSource(source)
    }
    fun chooseSource(id:String){
        if(!canEdit||id==get("applied_to"))return
        if(changed()){requestedSource=id;return}
        loadSource(id)
    }
    fun cancelSourceChange(){requestedSource=null}
    fun confirmSourceChange(){val id=requestedSource?:return;requestedSource=null;if(canEdit)loadSource(id)}
    private fun loadSource(id:String){
        val request=++sourceSequence
        if(id.isBlank()){set("applied_to","");returnSourceLines.clear();return}
        val originalDraft=body().toString()
        sourceLoading=true
        vm.task{
            try{
                val row=vm.api.record(companyId,id)
                if(vm.editor!==this||sourceSequence!=request||!vm.inWorkspace(companyId,workspaceStamp))return@task
                if(body().toString()!=originalDraft){vm.notice="Draft changed while source loaded. Review it and choose the source again.";return@task}
                val data=row.o("data")
                val stagedLines=row.a("return_capacity_lines").objects().ifEmpty{data.a("lines").objects()}.filter{additionalReturnQuantity(it.s("return_capacity_scope"),it.s("remaining_return_quantity")).toBigDecimalOrNull()?.signum()!=0}.map{row->LineState(row,regular).also{it.set("quantity",additionalReturnQuantity(row.s("return_capacity_scope"),row.s("remaining_return_quantity")))}}
                val stagedFields=mutableMapOf("applied_to" to id,"name" to row.s("name"),"document_discount_percent" to data.s("document_discount_percent").ifBlank{"0"})
                for(key in listOf("party_id","party_address","party_gstin","party_phone","shipping_address","place_of_supply","supplier_state"))stagedFields[key]=data.s(key)
                if(purchase)stagedFields["supplier_state"]=supplierOrigin(data)
                setReturnSourceLines(row)
                stagedFields.forEach{(key,value)->set(key,value)}
                lines.clear();lines.addAll(stagedLines);preview=null;previewError=""
            }catch(e:Exception){
                if(e is kotlinx.coroutines.CancellationException)throw e
                if(vm.editor===this&&sourceSequence==request&&vm.inWorkspace(companyId,workspaceStamp))throw e
            }finally{if(request==sourceSequence)sourceLoading=false}
        }
    }
    fun body():JSONObject {
        val values=JSONObject()
        if(master){values.put("is_active",flag("is_active"));if(kind=="party")values.put("credit_limit",get("credit_limit").ifBlank{null}?:JSONObject.NULL);for(key in if(kind=="party")listOf("gstin","address","shipping_address","phone","email","party_type")else listOf("hsn","unit","sale_rate","purchase_rate","gst_rate","barcode","item_type","tax_treatment","image_data_url","image_thumbnail"))values.put(key,get(key));if(kind=="item"){values.put("track_stock",flag("track_stock"));values.put("low_stock_threshold",get("low_stock_threshold").ifBlank{null}?:JSONObject.NULL)}else values.put("payment_terms_days",if(get("payment_terms_days").isBlank())JSONObject.NULL else get("payment_terms_days").toIntOrNull()?:get("payment_terms_days"))}
        else {
            for(key in listOf("party_id","party_address","party_gstin","party_phone","shipping_address","place_of_supply","due_date","notes","terms","category"))values.put(key,get(key))
            if(payment||kind in setOf("expense","pos")){values.put("payment_account",get("payment_account"));if(get("payment_account")=="bank")values.put("bank_account_id",get("bank_account_id"))}
            if(document){values.put("lines",JSONArray(lines.map{it.json()}));values.put("supplier_state",get("supplier_state"));values.put("document_discount_percent",get("document_discount_percent"));values.put("round_total",flag("round_total"));values.put("return_stock",flag("return_stock"));if(get("applied_to").isNotBlank())values.put("applied_to",get("applied_to"));if(kind=="pos"&&get("tender_amount").isNotBlank())values.put("tender_amount",get("tender_amount"))}
            if(payment){values.put("is_advance",flag("is_advance"));values.put("advance_supply",get("advance_supply"));values.put("advance_gst_rate",get("advance_gst_rate"));values.put("allocations",JSONArray(if(flag("is_advance"))emptyList<JSONObject>()else allocations.map{JSONObject().put("document_id",it.documentId).put("amount",it.amount)}))}
        }
        if(master)ApiCapabilities.filterMaster(values,vm.supportedFeatures)
        if(previous!=null)values.put("version",previous.o("data").optInt("version"));if(conversion!=null)values.put("source_document_id",conversion.s("id"))
        return JSONObject().put("kind",kind).put("name",get("name")).put("number",get("number")).put("date",get("date")).put("amount",if(document||master)"0"else get("amount")).put("data",values)
    }
    fun save(keepOpen:Boolean=false){
        if(saving||scanning||sourceLoading||quickAdding.isNotBlank()||!vm.inWorkspace(companyId,workspaceStamp))return
        saving=true
        vm.task{try{
            if(!retryPending){
                if(fixedReturnReviewNeeded)throw Exception("Review the fixed discount against the quantities being returned before saving. It is not automatically prorated.")
                if(get("name").isBlank())throw Exception("Enter a party or description.")
                if(master&&ApiCapabilities.unsupportedChanges(initialMasterFields,fields,vm.supportedFeatures).isNotEmpty())throw Exception("Some edited settings are not supported by this server. Upgrade the API before saving these changes; they have not been saved.")
                if(master)masterPlanningIssue(kind,get("payment_terms_days"),get("low_stock_threshold"),get("credit_limit"))?.let{throw Exception(it)}
                if(payment&&!flag("is_advance")&&(allocations.isEmpty()||allocations.any{it.documentId.isBlank()}))throw Exception("Allocate the payment or record an advance.")
            }
            val command=submission.recordCommand(::body,::paymentBody)
            val body=command.getJSONObject("record")
            val pay=command.optJSONObject("payment")
            var savedId=""
            try {
                if(master&&previous!=null){val flat=copy(body.o("data")).put("name",body.s("name"));vm.api.request(vm.api.company(companyId,"/masters/${previous.s("id")}"),"PUT",flat)}
                else if(pay!=null)savedId=vm.api.saveRecordWithPayment(companyId,body,pay,retryKey).o("document").s("id")
                else savedId=vm.api.saveRecord(companyId,body,retryKey,previous).s("id")
                submission.succeeded();retryPending=false
            }catch(e:Exception){submission.failed(e);retryPending=submission.unresolved;throw e}
            if(!vm.inWorkspace(companyId,workspaceStamp))return@task
            if(vm.editor===this)vm.editor=if(keepOpen&&canSaveAndNew)EntryEditor(vm,kind)else null
            // Like Vyapar / Swipe: a newly saved customer document opens ready to share, print or collect.
            if(!keepOpen&&previous==null&&conversion==null&&savedId.isNotBlank()&&kind in setOf("sales_invoice","estimate","proforma","sales_order","credit_note"))vm.detail=JSONObject().put("id",savedId)
            // Saving succeeded even if the subsequent list refresh fails. Never resubmit it.
            vm.notice=if(keepOpen&&canSaveAndNew)"Saved. Ready for the next document."else"Saved successfully."
            vm.refresh()
        }finally{saving=false}}
    }
    fun scan(uri:android.net.Uri){if(scanning)return;scanning=true;vm.task{try{val image=vm.files.image(uri,3000,2_700_000);val result=vm.api.request(vm.api.company(companyId,"/ocr/purchase-draft"),"POST",JSONObject().put("image_data_url",image)) as JSONObject;if(vm.editor!==this)return@task;val draft=result.o("draft");for((target,source)in mapOf("name" to "supplier_name","party_gstin" to "supplier_gstin","party_address" to "supplier_address","number" to "invoice_number"))set(target,draft.s(source));set("date",draft.s("invoice_date").ifBlank{today()});set("place_of_supply",draft.s("place_of_supply").ifBlank{vm.company.s("state_code")});set("supplier_state",get("party_gstin").take(2).ifBlank{vm.company.s("state_code")});for(key in listOf("party_id","party_phone","shipping_address","due_date"))set(key,"");set("document_discount_percent","0");set("round_total","false");lines.clear();draft.a("items").objects().forEach{item->lines.add(LineState(JSONObject().put("description",item.s("description")).put("quantity",item.s("quantity").ifBlank{"1"}).put("rate",item.s("rate")).put("gst_rate",item.s("gst_rate")).put("hsn",item.s("hsn")),regular,importedFromOcr=true))};ocrTotal=draft.s("total");vm.notice="OCR prepared a draft. Review every field and link stock items before saving."}finally{scanning=false}}}
}
