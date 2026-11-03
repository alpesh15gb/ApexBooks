package com.apexbooks.accounting

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONArray
import org.json.JSONObject

@Composable fun ReportsScreen(vm:AppModel){
    var selected by remember(vm.companyId){mutableStateOf<Feature?>(null)}
    var search by remember(vm.companyId){mutableStateOf("")};var group by remember(vm.companyId){mutableStateOf("all")}
    val feature=selected
    if(feature==null){
        val reports=vm.reports.filter{(it.key!="statements"||vm.supports("financial_statements"))&&(group=="all"||it.group==group)&&(it.title+" "+it.description+" "+it.group).contains(search.trim(),true)}
        LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)){
            item{Heading("Know your numbers","Financial statements, GST and business insights.")}
            item{SearchBarField("Search reports",search){search=it}}
            item{Row(Modifier.horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(8.dp)){(listOf("all" to "All reports")+vm.reports.map{it.group}.distinct().map{it to it}).forEach{(key,label)->FilterChip(selected=group==key,onClick={group=key},label={Text(label)})}}}
            reports.groupBy{it.group}.forEach{(category,features)->
                item{Column(verticalArrangement=Arrangement.spacedBy(10.dp)){
                    Text(category.uppercase(),style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant,fontWeight=FontWeight.Bold)
                    Surface(shape=RoundedCornerShape(20.dp),color=Color.White){Column{features.forEachIndexed{index,report->
                        val available=!report.key.startsWith("gstr")||vm.regular
                        NativeActionRow(report.title,if(available)report.description else "Requires regular GST registration",if(report.key.startsWith("gstr"))Icons.Outlined.ReceiptLong else Icons.Outlined.BarChart){if(available)selected=report}
                        if(index<features.lastIndex)HorizontalDivider(Modifier.padding(start=74.dp))
                    }}}
                }}
            }
            if(reports.isEmpty())item{Section{Text("No reports match this search.")}}
        };return
    }
    BackHandler{selected=null}
    val cid=vm.companyId;val gst=feature.key.startsWith("gstr")
    var from by remember(feature.key){mutableStateOf(financialStart())};var to by remember(feature.key){mutableStateOf(today())};var anchor by remember(feature.key){mutableStateOf(today())};var mode by remember(feature.key){mutableStateOf("month")};var party by remember(feature.key){mutableStateOf("")};var apply by remember(feature.key){mutableIntStateOf(0)}
    var value by remember(feature.key){mutableStateOf<Any?>(null)};var ready by remember(feature.key){mutableStateOf("")};var filename by remember(feature.key){mutableStateOf("")};var loading by remember(feature.key){mutableStateOf(false)};var failure by remember(feature.key){mutableStateOf("")}
    val range=runCatching{if(gst)reportPeriod(mode,anchor,from,to)else reportPeriod("custom",anchor,from,to)}.getOrNull()
    fun path(dates:Pair<String,String>):String{val query=if(feature.key in setOf("ageing","credits","advances"))"as_of=${dates.second}"else"from_date=${dates.first}&to_date=${dates.second}";return vm.api.company(cid,feature.path+(if(feature.path.contains('?'))"&"else"?")+query+(if(feature.key in setOf("ageing","parties"))"&party=${encode(party)}"else""))}
    val wanted=range?.let{path(it)}?:""
    LaunchedEffect(cid,feature.key,apply,vm.revision){
        ready="";value=null;loading=true;failure=""
        try{val dates=requireNotNull(range){"Choose a valid date range. The end date must follow the start date."};val url=path(dates);val result=vm.api.request(url);currentCoroutineContext().ensureActive();value=result;ready=url;filename=(if(feature.key=="gstr2a")"gstr2a-purchase-books"else if(gst)feature.key+"-preparation"else feature.key)+"-${dates.first}-${dates.second}"}
        catch(e:Exception){currentCoroutineContext().ensureActive();failure=e.message?:"This report could not be loaded.";vm.failure(e)}finally{loading=false}
    }
    fun export(format:String){if(ready.isBlank()||ready!=wanted)return;val url=ready;val name=filename;vm.task{val bytes=vm.api.bytes(url.substringBefore('?')+".$format?"+url.substringAfter('?'));if(vm.companyId!=cid||vm.page!="reports")return@task;if(format=="pdf")vm.pdf=PdfView(bytes,"$name.pdf")else vm.files.save(bytes,"$name.$format")}}
    val exportReady=ready.isNotBlank()&&ready==wanted&&!loading&&vm.busy==0
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(15.dp)){
        item{TextButton(onClick={selected=null}){Icon(Icons.Outlined.ArrowBack,null);Text("Report library")};Heading(feature.title,feature.description)}
        item{Section("Report period"){
            if(gst){Choice("GST period",mode,listOf("month" to "Full month","quarter" to "Full quarter","custom" to "Custom dates"),{mode=it});if(mode!="custom")DateField("Choose any date in the month / quarter",anchor,{anchor=it})}
            if(!gst||mode=="custom"){DateField("From",from,{from=it});DateField("To / as of",to,{to=it})}else range?.let{Text("${it.first} to ${it.second}",style=MaterialTheme.typography.bodyMedium)}
            if(feature.key in setOf("parties","ageing"))Field("Party filter · optional",party,{party=it})
            Button(onClick={apply++},enabled=!loading&&range!=null,modifier=Modifier.fillMaxWidth()){Text(if(loading)"Loading…"else"Apply period")}
            Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){OutlinedButton(onClick={export("pdf")},enabled=exportReady,modifier=Modifier.weight(1f)){Text("PDF / print")};OutlinedButton(onClick={export("xlsx")},enabled=exportReady,modifier=Modifier.weight(1f)){Text("Export XLSX")}}
            if(feature.key=="gstr1")OutlinedButton(onClick={export("json")},enabled=exportReady&&(value as? JSONObject)?.o("export_info")?.optBoolean("json_available")==true,modifier=Modifier.fillMaxWidth()){Text("Draft JSON")}
            if(ready.isNotBlank()&&ready!=wanted)Text("Apply the selected dates to refresh the report and exports.",style=MaterialTheme.typography.bodySmall)
        }}
        if(loading)item{Box(Modifier.fillMaxWidth().padding(30.dp),contentAlignment=Alignment.Center){CircularProgressIndicator()}}
        if(failure.isNotBlank())item{Section{Text(failure,color=MaterialTheme.colorScheme.error)}}
        value?.let{data->item{Column(verticalArrangement=Arrangement.spacedBy(15.dp)){if(gst&&data is JSONObject)GstReportContent(data)else if(feature.key=="statements"&&data is JSONObject&&data.has("profit_loss"))StatementsContent(data)else ReportContent(data)}}}
    }
}

@Composable private fun GstReportContent(data:JSONObject){
    fun total(key:String)=data.o(key).let{obj->obj.keys().asSequence().fold(java.math.BigDecimal.ZERO){a,k->a+(obj.s(k).toBigDecimalOrNull()?:java.math.BigDecimal.ZERO)}}
    Metric("Output GST",money(total("output")),Modifier.fillMaxWidth());Metric("Input from entered bills",money(total("book_itc")),Modifier.fillMaxWidth());Metric("Estimated cash payable",money(data.s("cash_total")),Modifier.fillMaxWidth())
    val info=data.o("export_info");val issues=info.a("issues").objects();var checks by remember(data){mutableStateOf(false)};var notes by remember(data){mutableStateOf(false)}
    Section("Export format and preparation checks"){
        Text(when(data.s("standard")){"GSTR-1"->"GSTN ${info.s("template")} worksheets. Review XLSX or draft JSON in the current offline tool before upload.";"GSTR-2A"->"Purchase-book reconciliation. Supplier filing details must come from portal GSTR-2A.";else->"Numbered 3B schedules. External records and actual payments remain blank until reviewed."},style=MaterialTheme.typography.bodyMedium)
        if(issues.isNotEmpty()){TextButton(onClick={checks=!checks}){Text("${issues.size} preparation checks"+if(data.s("standard")=="GSTR-1")" · JSON unavailable"else" · review before use")};if(checks)issues.forEach{Text(it.s("document")+": "+it.s("message"),style=MaterialTheme.typography.bodySmall)}}
        TextButton(onClick={notes=!notes}){Text("Included schedules and review notes")};if(notes){Text(info.a("schedules").objects().joinToString(" · "){it.s("name")+" ("+it.s("rows")+")"},style=MaterialTheme.typography.bodySmall);for(i in 0 until info.a("warnings").length())Text(info.a("warnings").optString(i),style=MaterialTheme.typography.bodySmall)}
    }
    if(data.has("return_tables")){data.a("return_tables").objects().forEach{table->GstSchedule(table.s("title"),(0 until table.a("headers").length()).map{table.a("headers").optString(it)},(0 until table.a("rows").length()).map{table.a("rows").getJSONArray(it)},(0 until table.a("money_columns").length()).map{table.a("money_columns").getInt(it)}.toSet())}}
    else{val columns=data.a("columns").objects();GstSchedule(data.s("title"),columns.map{it.s("label")},data.a("rows").objects().map{row->JSONArray(columns.map{row.opt(it.s("key"))?:JSONObject.NULL})},columns.mapIndexedNotNull{i,c->if(c.s("key") in setOf("taxable","cgst","sgst","igst","total","proposed_itc","ineligible"))i else null}.toSet())}
    Section{Text(data.s("note"),style=MaterialTheme.typography.bodySmall)}
    if(data.a("hsn").length()>0)GstSchedule("HSN / SAC summary",listOf("HSN / SAC","Rate","Quantity","Taxable","GST"),data.a("hsn").objects().map{JSONArray(listOf(it.s("hsn").ifBlank{"Not entered"},it.s("rate")+"%",it.s("quantity"),it.opt("taxable"),it.opt("tax")))},setOf(3,4))
}

@Composable private fun GstSchedule(title:String,headers:List<String>,rows:List<JSONArray>,moneyColumns:Set<Int>){
    var page by remember(rows){mutableIntStateOf(0)};val index=page.coerceIn(0,maxOf(0,(rows.size-1)/25))
    Section(title){
        if(rows.isEmpty())Text("No applicable entries in this period.")else{
            Text("Swipe sideways to review all columns.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Column(Modifier.horizontalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(10.dp)){
                Row{headers.forEachIndexed{i,label->Text(label,Modifier.width(if(i==0)220.dp else 155.dp).padding(8.dp),fontWeight=FontWeight.SemiBold,style=MaterialTheme.typography.labelMedium)}};HorizontalDivider()
                rows.drop(index*25).take(25).forEach{row->Row{headers.indices.forEach{i->val v=row.opt(i);Text(if(v==null||v==JSONObject.NULL)"Needs review"else if(i in moneyColumns)money(v.toString())else v.toString(),Modifier.width(if(i==0)220.dp else 155.dp).padding(8.dp),style=MaterialTheme.typography.bodySmall)}};HorizontalDivider()}
            }
            Text("${index*25+1}–${minOf((index+1)*25,rows.size)} of ${rows.size} rows",style=MaterialTheme.typography.bodySmall)
            if(rows.size>25)Row(horizontalArrangement=Arrangement.spacedBy(12.dp)){TextButton(enabled=index>0,onClick={page=index-1}){Text("Previous")};TextButton(enabled=(index+1)*25<rows.size,onClick={page=index+1}){Text("Next")}}
        }
    }
}
