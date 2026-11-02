@file:OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.apexbooks.accounting

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import java.math.BigDecimal
import java.time.LocalDate
import java.time.format.DateTimeFormatter

@Composable fun DashboardScreen(vm:AppModel){
    var period by rememberSaveable{mutableStateOf("year")}
    var summary by remember{mutableStateOf<JSONObject?>(null)}
    var financial by remember{mutableStateOf<JSONObject?>(null)}
    var gst by remember{mutableStateOf<JSONObject?>(null)}
    val end=LocalDate.now()
    val start=when(period){"month"->end.withDayOfMonth(1);"30days"->end.minusDays(29);else->LocalDate.parse(financialStart())}
    LaunchedEffect(vm.companyId,vm.revision,period){
        summary=null;financial=null;gst=null
        try{coroutineScope{
            val query="?from_date=$start&to_date=$end"
            val report=async{vm.api.request(vm.api.company(vm.companyId,"/reports/summary$query"))as JSONObject}
            val profit=async{vm.api.request(vm.api.company(vm.companyId,"/reports/financial$query"))as JSONObject}
            val tax=async{vm.api.request(vm.api.company(vm.companyId,"/reports/gst-payable?from_date=2000-01-01&to_date=$end"))as JSONObject}
            summary=report.await();financial=profit.await();gst=tax.await()
        }}catch(e:Exception){currentCoroutineContext().ensureActive();vm.failure(e)}
    }
    val bankCodes=vm.banks.map{it.s("ledger_code")}.toSet()
    val accounts=financial?.a("accounts")?.objects()?.filter{it.s("code")in setOf("SYS-CASH","SYS-BANK")||it.s("code")in bankCodes}.orEmpty()
    val invoices=vm.records.filter{it.s("kind")=="sales_invoice"&&it.optBoolean("posted")}
    val issued=invoices.fold(BigDecimal.ZERO){sum,r->sum+r.decimal("amount")}
    val outstanding=invoices.fold(BigDecimal.ZERO){sum,r->sum+r.decimal("outstanding")}
    val settled=(issued-outstanding).max(BigDecimal.ZERO)
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(18.dp),verticalArrangement=Arrangement.spacedBy(16.dp)){
        item{Column(verticalArrangement=Arrangement.spacedBy(8.dp)){
            Text("AT A GLANCE",style=MaterialTheme.typography.labelSmall,color=ApexGreen,fontWeight=FontWeight.Bold,letterSpacing=1.sp)
            Heading("Business overview","${start.format(DateTimeFormatter.ofPattern("d MMM yyyy"))} – ${end.format(DateTimeFormatter.ofPattern("d MMM yyyy"))}")
            Row(Modifier.horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(8.dp)){
                for((key,label)in listOf("year" to "Financial year","month" to "This month","30days" to "30 days"))FilterChip(selected=period==key,onClick={period=key},label={Text(label)})
            }
        }}
        if(!vm.recordsReady)item{Section("Loading transaction history"){Text("Live report totals are shown as they arrive. Collections, charts and billing become available when the full company history is ready.");if(vm.busy==0)OutlinedButton(onClick={vm.task{vm.refresh()}}){Text("Retry company data")}}}
        if(vm.recordsReady&&vm.records.none{it.optBoolean("posted")})item{Section("Start your books"){
            Text("Create your first invoice or purchase. Customers and items can be added now or entered while billing.")
            if(vm.canWrite){
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){Button(onClick={vm.add("sales_invoice")},modifier=Modifier.weight(1f)){Text("First invoice")};OutlinedButton(onClick={vm.add("purchase_bill")},modifier=Modifier.weight(1f)){Text("First purchase")}}
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){TextButton(onClick={vm.add("party")}){Text("Add party · optional")};TextButton(onClick={vm.add("item")}){Text("Add item · optional")}}
            }else Text("You have read-only access. Ask the owner to add records or invite you as an editor.",style=MaterialTheme.typography.bodySmall)
        }}
        val overdue=invoices.filter{it.decimal("outstanding").signum()>0&&it.o("data").s("due_date").isNotBlank()&&it.o("data").s("due_date")<today()}.sortedBy{it.o("data").s("due_date")}
        if(overdue.isNotEmpty())item{Section("Needs attention · ${overdue.size} overdue"){
            Text("Open an invoice to record a receipt or review the balance.",style=MaterialTheme.typography.bodySmall)
            overdue.take(3).forEach{row->TextButton(onClick={vm.detail=row},modifier=Modifier.fillMaxWidth()){Text("${row.s("number")} · ${row.s("name")} · ${money(row.s("outstanding"))} due")}}
            if(overdue.size>3)TextButton(onClick={vm.navigate("sales_invoice")}){Text("View all sales invoices →")}
        }}
        item{Box(Modifier.fillMaxWidth().background(Brush.linearGradient(listOf(Color(0xFF145FC4),Color(0xFF3083E8))),RoundedCornerShape(24.dp)).padding(20.dp)){
            Column(verticalArrangement=Arrangement.spacedBy(12.dp)){
                Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("Net sales",color=Color(0xFFDDEBFF),style=MaterialTheme.typography.labelLarge,fontWeight=FontWeight.Medium);Icon(Icons.Outlined.TrendingUp,null,tint=Color(0xFFBFE5FF))}
                Text(summary?.let{money(it.s("sales"))}?:"—",color=Color.White,fontSize=30.sp,fontWeight=FontWeight.Bold)
                Text("Posted sales, after credit notes",color=Color(0xFFDDEBFF),style=MaterialTheme.typography.bodySmall)
            }
        }}
        item{Row(horizontalArrangement=Arrangement.spacedBy(12.dp)){Metric("Net profit",financial?.let{money(it.s("net_profit"))}?:"—",Modifier.weight(1f));Metric("To collect · to date",summary?.let{money(it.s("receivables"))}?:"—",Modifier.weight(1f))}}
        item{Row(horizontalArrangement=Arrangement.spacedBy(12.dp)){Metric("To pay · to date",summary?.let{money(it.s("payables"))}?:"—",Modifier.weight(1f));Metric("Cash & bank",financial?.takeIf{vm.recordsReady}?.let{money(accounts.fold(BigDecimal.ZERO){sum,a->sum+a.decimal("closing_balance")})}?:"—",Modifier.weight(1f))}}
        if(vm.canWrite&&vm.recordsReady)item{Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){Button(onClick={vm.add("sales_invoice")},modifier=Modifier.weight(1f),contentPadding=PaddingValues(10.dp,14.dp)){Icon(Icons.Outlined.Add,null,Modifier.size(18.dp));Text("New invoice")};OutlinedButton(onClick={vm.add("purchase_bill")},modifier=Modifier.weight(1f),contentPadding=PaddingValues(10.dp,14.dp)){Icon(Icons.Outlined.DocumentScanner,null,Modifier.size(18.dp));Text("Add purchase")}}}
        if(vm.recordsReady)item{Section("Sales & purchases"){MonthlyPerformance(vm.records,start,end);Text("Posted invoice values, including GST where applicable",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
        if(vm.recordsReady)item{Section("Invoice collections"){
            Text("GET PAID",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            val fraction=if(issued>BigDecimal.ZERO)(settled.toFloat()/issued.toFloat()).coerceIn(0f,1f)else 0f
            Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(18.dp)){
                Box(Modifier.size(126.dp),contentAlignment=Alignment.Center){CircularProgressIndicator(progress={fraction},modifier=Modifier.fillMaxSize(),strokeWidth=12.dp,color=ApexGreen,trackColor=Color(0xFFE5EFED));Column(horizontalAlignment=Alignment.CenterHorizontally){Text("${(fraction*100).toInt()}%",style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.Bold);Text("settled",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
                Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(8.dp)){Text("Settled",style=MaterialTheme.typography.bodySmall);Text(money(settled),fontWeight=FontWeight.SemiBold);Text("Outstanding",style=MaterialTheme.typography.bodySmall);Text(money(outstanding),fontWeight=FontWeight.SemiBold)}
            }
            Text("All posted invoices · payments, advances and credits included.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            TextButton(onClick={vm.navigate("sales_invoice")}){Text("View sales invoices  →")}
        }}
        item{Section("Profit & loss"){
            Text(financial?.let{money(it.s("net_profit"))}?:"—",style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.Bold)
            Text("Net profit for this period",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            for((key,label)in listOf("income" to "Income","expenses" to "Costs & expenses"))Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(label);Text(financial?.let{money(it.s(key))}?:"—",fontWeight=FontWeight.Medium)}
            TextButton(onClick={vm.navigate("reports")}){Text("Explore reports  →")}
        }}
        if(vm.recordsReady)item{Section("Cash & bank"){
            for(account in accounts)Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(account.s("name"),Modifier.weight(1f));Text(money(account.s("closing_balance")),fontWeight=FontWeight.Medium)}
            TextButton(onClick={vm.navigate("bank")}){Text("Manage cash & bank  →")}
        }}
        if(vm.regular)item{Section("GST position · to date"){
            Text(gst?.let{money(it.s("cash_total"))}?:"—",style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.Bold,color=ApexGreen)
            Text("Estimated GST payable",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            for((key,label)in listOf("output" to "Output GST","book_itc" to "Input from entered bills")){val total=gst?.o(key)?.let{o->o.keys().asSequence().fold(BigDecimal.ZERO){sum,k->sum+o.decimal(k)}};Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(label);Text(total?.let{money(it)}?:"—",fontWeight=FontWeight.Medium)}}
            Text("Estimate from entered bills. Verify ITC eligibility and GSTR-2B before filing.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }}else item{Section("Your tax settings"){Text(if(vm.company.s("tax_mode")=="composition")"Composition accounting is active. Review composition reports for your liability."else"Non-GST accounting is active. Documents use your non-GST settings.")}}
        item{Heading("Recent activity")}
        items(vm.records.filter{it.s("kind") !in setOf("party","item","bank_account")}.take(8),key={it.s("id")}){RecordCard(vm,it)}
        item{Spacer(Modifier.height(88.dp))}
    }
}

private data class MonthMovement(val label:String,val sales:BigDecimal,val purchases:BigDecimal)
@Composable private fun MonthlyPerformance(records:List<JSONObject>,start:LocalDate,end:LocalDate){
    val movements=remember(records,start,end){
        generateSequence(start.withDayOfMonth(1)){it.plusMonths(1)}.takeWhile{!it.isAfter(end)}.take(13).map{month->
            val rows=records.filter{it.optBoolean("posted")&&it.s("date")>=start.toString()&&it.s("date")<=end.toString()&&it.s("date").startsWith(month.toString().take(7))}
            MonthMovement(month.format(DateTimeFormatter.ofPattern("MMM")),rows.fold(BigDecimal.ZERO){sum,r->sum+when(r.s("kind")){"sales_invoice","pos"->r.decimal("amount");"credit_note"->-r.decimal("amount");else->BigDecimal.ZERO}},rows.fold(BigDecimal.ZERO){sum,r->sum+when(r.s("kind")){"purchase_bill"->r.decimal("amount");"debit_note"->-r.decimal("amount");else->BigDecimal.ZERO}})
        }.toList()
    }
    Row(horizontalArrangement=Arrangement.spacedBy(16.dp)){Text("● Net sales",style=MaterialTheme.typography.labelSmall,color=ApexGreen);Text("● Net purchases",style=MaterialTheme.typography.labelSmall,color=Color(0xFF658CA2))}
    val values=movements.flatMap{listOf(it.sales.toFloat(),it.purchases.toFloat())};val max=maxOf(0f,values.maxOrNull()?:0f);val min=minOf(0f,values.minOrNull()?:0f);val span=max-min
    if(span==0f){Box(Modifier.fillMaxWidth().height(140.dp),contentAlignment=Alignment.Center){Text("No net movement in this period",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)};return}
    val description=movements.joinToString("; "){"${it.label}: net sales ${money(it.sales)}, net purchases ${money(it.purchases)}"}
    Column{
        Canvas(Modifier.fillMaxWidth().height(150.dp).semantics{contentDescription=description}){
            val top=10.dp.toPx();val height=size.height-16.dp.toPx();fun y(value:Float)=top+(max-value)/span*height
            for(value in listOf(max,(max+min)/2,min))drawLine(Color(0xFFE5ECEF),Offset(0f,y(value)),Offset(size.width,y(value)),1.dp.toPx())
            val base=y(0f);val step=size.width/movements.size;val width=minOf(18.dp.toPx(),step*.27f)
            movements.forEachIndexed{i,row->for((value,color,shift)in listOf(Triple(row.sales.toFloat(),ApexGreen,-width-2.dp.toPx()),Triple(row.purchases.toFloat(),Color(0xFF86ABC0),2.dp.toPx()))){val at=y(value);drawRect(color,Offset(i*step+step/2+shift,minOf(at,base)),Size(width,kotlin.math.abs(base-at)))}}
        }
        Row(Modifier.fillMaxWidth()){movements.forEach{Box(Modifier.weight(1f),contentAlignment=Alignment.Center){Text(it.label,fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}}}
    }
}
