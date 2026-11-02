package com.apexbooks.accounting

import androidx.compose.material3.*
import androidx.compose.runtime.*
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import org.json.JSONObject

/** Informational server-calculated exposure only: never an authority to approve or block posting. */
@Composable fun CustomerCreditStatus(vm:AppModel,partyId:String,asOf:String,proposedAmount:String) {
    val cid=vm.companyId;val stamp=vm.workspaceStamp()
    var report by remember(cid,partyId,asOf,proposedAmount){mutableStateOf<JSONObject?>(null)}
    var failure by remember(cid,partyId,asOf,proposedAmount){mutableStateOf("")}
    var reload by remember{mutableIntStateOf(0)}
    LaunchedEffect(cid,partyId,asOf,proposedAmount,reload){
        report=null;failure="";delay(350)
        try{
            val response=vm.api.request(vm.api.company(cid,"/parties/${encode(partyId)}/credit-status?as_of=${encode(asOf)}&proposed_amount=${encode(proposedAmount)}"))as JSONObject
            currentCoroutineContext().ensureActive();if(vm.inWorkspace(cid,stamp))report=response
        }catch(e:Exception){currentCoroutineContext().ensureActive();if(vm.inWorkspace(cid,stamp)){failure="Credit check unavailable. You can retry; saving is not blocked by this check.";if(e is ApiFailure&&e.status==401)vm.failure(e)}}
    }
    Section("Customer credit exposure"){
        Text("As of $asOf · informational warning only",style=MaterialTheme.typography.bodySmall)
        if(failure.isNotBlank()){Text(failure,color=MaterialTheme.colorScheme.error);TextButton(onClick={reload++}){Text("Retry credit check")}}
        else if(report==null)Text("Checking posted balances…",style=MaterialTheme.typography.bodySmall)
        report?.let{row->
            DetailValue("Current net exposure",money(row.s("current_exposure")))
            if(proposedAmount.toBigDecimalOrNull()?.signum()!=0){DetailValue("Proposed sale",money(row.s("proposed_amount")));DetailValue("Projected exposure",money(row.s("projected_exposure")))}
            if(row.isNull("credit_limit"))Text("No credit limit is set for this customer.",style=MaterialTheme.typography.bodySmall)
            else {
                DetailValue("Credit limit",money(row.s("credit_limit")));DetailValue("Remaining credit",money(row.s("remaining_credit")))
                if(row.optBoolean("exceeded"))Text("Credit limit exceeded. Review the customer's balance or collect payment before extending more credit. You can still save this document.",color=MaterialTheme.colorScheme.error)
                else Text("Within the configured limit at the time of this check.",style=MaterialTheme.typography.bodySmall)
            }
            Text("Receivables less unused customer advances and credits. Other users may post changes after this check; this is not a credit approval.",style=MaterialTheme.typography.bodySmall)
        }
    }
}
