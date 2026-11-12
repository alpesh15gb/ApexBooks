package com.apexbooks.accounting

import androidx.compose.material3.*
import androidx.compose.runtime.*
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.CancellationException
import org.json.JSONObject

@Composable fun PeriodLockTool(vm:AppModel) {
    val cid=vm.companyId
    var loaded by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(true) }
    var failure by remember { mutableStateOf("") }
    var current by remember { mutableStateOf("") }
    var date by remember { mutableStateOf("") }
    var confirmed by remember { mutableStateOf("") }
    var attempt by remember { mutableIntStateOf(0) }
    LaunchedEffect(cid,attempt) {
        loading=true;loaded=false;confirmed="";failure=""
        try {
            val result=vm.api.request(vm.api.company(cid,"/period-lock")) as JSONObject
            current=result.s("locked_through");loaded=true
        } catch(e:CancellationException) { throw e }
          catch(e:Exception) { failure=e.message?:"Could not load the current lock." }
        finally { loading=false }
    }
    val valid=loaded&&!loading&&date.matches(Regex("\\d{4}-\\d{2}-\\d{2}"))&&date>current&&confirmed==date
    ActionDialog("Lock accounting period",vm,confirm="Confirm period lock",enabled=valid,
        hasChanges={date.isNotBlank()},onDismiss={vm.tool=""},onSave={
            check(valid) { "Load the current lock and confirm the exact date first." }
            java.time.LocalDate.parse(date)
            vm.api.request(vm.api.company(cid,"/period-lock"),"PUT",JSONObject().put("locked_through",date))
            vm.tool=""
        }) {
        when { loading -> Text("Loading current period lock…")
            !loaded -> { Text(failure);OutlinedButton(onClick={attempt++}) { Text("Retry loading") } }
            else -> Text(if(current.isBlank()) "No date set" else "Currently locked through $current") }
        Text("Entries through the selected date cannot be added or edited. The lock can only move forward.")
        DateField("New lock date",date,{date=it;confirmed=""})
        if(loaded&&date.isNotBlank()&&date>current) Toggle("I confirm locking all entries through $date",confirmed==date,{confirmed=if(it)date else ""})
    }
}

@Composable fun CashBookTool(vm:AppModel) {
    val cid=vm.companyId
    var from by remember { mutableStateOf(financialStart()) }
    var to by remember { mutableStateOf(today()) }
    var bank by remember { mutableStateOf("default") }
    var requested by remember { mutableStateOf(Triple(from,to,bank)) }
    var attempt by remember { mutableIntStateOf(0) }
    var applied by remember { mutableStateOf<Triple<String,String,String>?>(null) }
    var report by remember { mutableStateOf<Any?>(null) }
    var failure by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(true) }
    fun query(filters:Triple<String,String,String>)="?from_date=${filters.first}&to_date=${filters.second}&bank_account_id=${encode(filters.third)}"
    LaunchedEffect(cid,requested,attempt) {
        loading=true;failure=""
        val snapshot=requested
        try {
            val result=vm.api.request(vm.api.company(cid,"/cash-book"+query(snapshot)))
            report=result;applied=snapshot
        } catch(e:CancellationException) { throw e }
          catch(e:Exception) { failure=e.message?:"Could not load cash book." }
        finally { loading=false }
    }
    ActionDialog("Cash and bank book",vm,confirm="Done",onDismiss={vm.tool=""},onSave={vm.tool=""}) {
        Choice("Bank account · cash included",bank,vm.banks.map{it.s("id") to it.s("name")},{bank=it})
        DateField("From",from,{from=it});DateField("To",to,{to=it})
        Button(onClick={requested=Triple(from,to,bank);attempt++}) { Text("Apply dates") }
        if(loading) Text("Loading report…")
        if(failure.isNotBlank()) Text(failure)
        Text("Exports use the filters of the displayed report. Apply edited filters to update it.")
        applied?.let { Text("Displayed: ${it.first} to ${it.second}") }
        for(fmt in listOf("pdf","xlsx")) OutlinedButton(enabled=applied!=null,onClick={
            val snapshot=applied?:return@OutlinedButton
            vm.task { vm.files.save(vm.api.bytes(vm.api.company(cid,"/cash-book.$fmt"+query(snapshot))),"cash-book.$fmt") }
        }) { Text("Export ${fmt.uppercase()}") }
        ReportContent(report)
    }
}
