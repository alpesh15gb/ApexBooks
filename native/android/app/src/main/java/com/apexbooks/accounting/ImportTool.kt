package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.format.DateTimeFormatterBuilder
import java.time.format.ResolverStyle
import java.util.Locale

@Composable fun ImportTool(vm:AppModel){val tool=vm.tool;val cid=vm.companyId;var raw by remember{mutableStateOf<ByteArray?>(null)};var report by remember{mutableStateOf<JSONObject?>(null)};var prepared by remember{mutableStateOf<JSONObject?>(null)};var preparedInput by remember{mutableStateOf("")};var name by remember{mutableStateOf("")};var password by remember{mutableStateOf("")};var kind by remember{mutableStateOf("party")};var accepted by remember{mutableStateOf(false)};var scope by remember{mutableStateOf("posting")};var header by remember{mutableStateOf("1")};var dateFormat by remember{mutableStateOf("dd/MM/uuuu")};val mapping=remember{mutableStateMapOf<String,String>()};var table by remember{mutableStateOf(emptyList<List<String>>())};val bank=vm.toolData?.s("bank_account_id")?.ifBlank{"default"}?:"default"
    val aliases=mapOf("date" to listOf("date","transaction date","txn date","value date"),"description" to listOf("description","narration","particulars","transaction details"),"reference" to listOf("reference","ref","utr","cheque/ref no","chq/ref no"),"amount" to listOf("amount","signed amount"),"debit" to listOf("debit","withdrawal","withdrawals","debit amount"),"credit" to listOf("credit","deposit","deposits","credit amount"))
    fun reset(){report=null;prepared=null;accepted=false}
    fun remap(){mapping.clear();val row=table.getOrNull((header.toIntOrNull()?:1)-1)?:return;for((key,names)in aliases){val index=row.indexOfFirst{it.trim().lowercase()in names};mapping[key]=if(index>=0)index.toString()else""};reset()}
    fun identity()=listOf(name,password,kind,scope,header,dateFormat,mapping.toSortedMap().toString()).joinToString("|")
    fun body():JSONObject {
        val bytes=raw?:throw Exception("Choose a backup or CSV file first.")
        if(tool=="vyapar"){if(bytes.size>3_000_000)throw Exception("Choose a .vyb backup under 3 MB.");return JSONObject().put("backup_base64",NativeFiles.b64(bytes))}
        if(tool=="restore")return JSONObject().put("company_name",name).put("backup_base64",NativeFiles.b64(NativeFiles.prepareRestore(bytes,password)))
        if(table.size<2)throw Exception("The CSV needs a header and data rows.")
        if(tool=="master_import"){
            if(table.size>501)throw Exception("Import 1–500 parties or items at a time.");val headers=table[0].map{it.trim().lowercase().replace(' ','_')};if("name" !in headers)throw Exception("The CSV needs a name column. Export parties or items for a template.")
            val supported=setOf("name","gstin","address","phone","email","party_type","hsn","unit","sale_rate","purchase_rate","gst_rate","barcode","item_type","tax_treatment","track_stock","image_data_url","image_thumbnail");val rows=table.drop(1).map{cells->JSONObject().also{row->headers.forEachIndexed{index,key->if(key in supported&&index<cells.size){val value=cells[index];row.put(key,when(key){"track_stock"->value.equals("true",true)||value=="1"||value.equals("yes",true);"sale_rate","purchase_rate","gst_rate"->Csv.amount(value.trimEnd('%'));else->value})}}}}
            return JSONObject().put("kind",kind).put("rows",JSONArray(rows))
        }
        val start=header.toIntOrNull()?:throw Exception("Enter the header row number.");if(start<1||start>=table.size)throw Exception("Choose a header before the transaction rows.");if(mapping["date"].isNullOrBlank()||mapping["description"].isNullOrBlank()||mapping["amount"].isNullOrBlank()&&(mapping["debit"].isNullOrBlank()||mapping["credit"].isNullOrBlank()))throw Exception("Map date, description, and signed amount or debit and credit.")
        val formatter=DateTimeFormatterBuilder().parseCaseInsensitive().appendPattern(dateFormat).toFormatter(Locale.ENGLISH).withResolverStyle(ResolverStyle.STRICT)
        val rows=table.drop(start).mapIndexed{index,cells->fun get(key:String)=mapping[key]?.toIntOrNull()?.let{cells.getOrNull(it)}?:""
try{val date=LocalDate.parse(get("date"),formatter).toString();val amount=if(!mapping["amount"].isNullOrBlank())Csv.amount(get("amount"))else{val debit=Csv.amount(get("debit")).toBigDecimal();val credit=Csv.amount(get("credit")).toBigDecimal();if(debit.signum()<0||credit.signum()<0||debit.signum()>0&&credit.signum()>0)throw Exception("Use one positive debit or credit.");(credit-debit).toPlainString()};if(amount.toBigDecimal().signum()==0)throw Exception("Amount is zero.");if(get("description").isBlank())throw Exception("Description is empty.");JSONObject().put("date",date).put("description",get("description")).put("reference",get("reference")).put("amount",amount)}catch(e:Exception){throw Exception("CSV row ${start+index+1}: ${e.message}")}}
        return JSONObject().put("bank_account_id",bank).put("lines",JSONArray(rows))
    }
    fun endpoint(stage:String)=when(tool){"restore"->"/api/backups/restore/$stage";"vyapar"->vm.api.company(cid,"/imports/${if(scope=="posting")"vyapar-posting"else"vyapar"}/$stage");"master_import"->vm.api.company(cid,"/masters/import");else->vm.api.company(cid,"/bank-statement/import")}
    val title=when(tool){"restore"->"Restore company backup";"vyapar"->"Import Vyapar backup";"master_import"->"Import parties / items CSV";else->"Import bank statement CSV"}
    ActionDialog(title,vm,confirm=if(tool=="restore")"Restore reviewed backup"else if(tool=="vyapar"&&scope=="posting")"Post and reconcile migration"else"Import reviewed data",enabled=prepared!=null&&accepted,onDismiss={vm.tool="";vm.toolData=null},onSave={val payload=prepared?:throw Exception("Validate and review the preview first.");if(identity()!=preparedInput)throw Exception("The options changed. Validate and review the preview again.");if(tool=="vyapar"&&scope=="posting"&&report?.optBoolean("ready")!=true)throw Exception("The migration must pass every blocking check before posting.");if(report?.a("errors")?.length()?.let{it>0}==true)throw Exception("Resolve the preview errors before importing.");val result=vm.api.request(endpoint("commit"),"POST",payload)as JSONObject;vm.tool="";vm.toolData=null;if(tool=="restore")vm.loadCompanies(result.s("company_id"))else vm.refresh();vm.notice=if(tool=="vyapar"&&scope=="posting")"Migration posted and reconciled."else"Import completed."}){
        Text(if(tool=="restore")"The backup restores into a separate company. Existing books are preserved."else if(tool=="vyapar")"Preview the mapping and reconciliation before posting. Unsupported source data blocks posting without changing your books."else"Review validation and the first rows before importing.")
        OutlinedButton(onClick={vm.files.pick{uri->vm.task{val bytes=vm.files.read(uri,if(tool=="restore")50_000_000 else 3_000_000);raw=bytes;reset();if(tool in setOf("master_import","statement_import")){table=Csv.parse(bytes.toString(Charsets.UTF_8));remap()}}}}){Text(if(raw==null)"Choose file"else"Choose another file · ${raw!!.size} bytes")}
        if(tool=="restore"){Field("Restored company name",name,{name=it;reset()},maximum=120);Field("Backup password · when encrypted",password,{password=it;reset()},password=true,maximum=128)}
        if(tool=="vyapar")Choice("Import scope",scope,listOf("posting" to "Full transaction posting","archive" to "Parties, items and source archive only"),{scope=it;reset()})
        if(tool=="master_import")Choice("Import type",kind,listOf("party" to "Parties","item" to "Items"),{kind=it;reset()})
        if(tool=="statement_import"&&table.isNotEmpty()){Field("Header row number",header,{header=it;remap()},number=true,maximum=5);Choice("Date format",dateFormat,listOf("dd/MM/uuuu" to "DD/MM/YYYY","uuuu-MM-dd" to "YYYY-MM-DD","MM/dd/uuuu" to "MM/DD/YYYY","dd-MM-uuuu" to "DD-MM-YYYY","dd-MMM-uuuu" to "DD-MMM-YYYY"),{dateFormat=it;reset()});val names=table.getOrNull((header.toIntOrNull()?:1)-1)?:emptyList();for(key in aliases.keys)Choice("${friendly(key)} column",mapping[key]?:"",listOf("" to "Not mapped")+names.mapIndexed{i,s->i.toString() to "${i+1}. $s"},{mapping[key]=it;reset()})}
        Button(enabled=raw!=null,onClick={vm.task{val payload=withContext(Dispatchers.Default){body()};val preview=copy(payload);if(tool in setOf("master_import","statement_import"))preview.put("dry_run",true);val result=vm.api.request(endpoint("preview"),"POST",preview)as JSONObject;if(tool in setOf("restore","vyapar"))payload.put("digest",result.s("digest"));if(tool in setOf("master_import","statement_import"))payload.put("dry_run",false);prepared=payload;preparedInput=identity();report=result;accepted=false}}){Text("Validate and preview")}
        report?.let{ReportContent(it,"Preview");val rows=prepared?.a(if(tool=="master_import")"rows"else"lines")?:JSONArray();if(rows.length()>0)ReportContent(JSONArray(rows.objects().take(10)),"First 10 rows");Toggle("I reviewed the preview and want to import this data.",accepted,{accepted=it})}
    }
}
