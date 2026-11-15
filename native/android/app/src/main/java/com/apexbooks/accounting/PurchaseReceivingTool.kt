package com.apexbooks.accounting

import android.net.Uri
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import org.json.JSONObject
import java.util.UUID

@Composable
internal fun PurchaseReceivingTool(vm: AppModel) {
    val order = vm.toolData ?: return
    val cid = vm.companyId
    val orderId = order.s("id")
    val scope = "purchase_receive:$orderId"
    val draft = remember(cid, scope) { vm.toolDraft(scope) }
    val current = remember(cid, order) { vm.captureReadOwner("purchase_receive", order) }
    val values = draft.values
    val submission = draft.submission
    val encodedOrder = Uri.encode(orderId)
    var snapshot by remember { mutableStateOf<JSONObject?>(null) }
    var loadError by remember { mutableStateOf("") }
    var quoteError by remember { mutableStateOf("") }
    var quote by remember { mutableStateOf<Pair<String, String>?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    var sending by remember { mutableStateOf(false) }
    var unresolved by remember { mutableStateOf(submission.unresolved) }
    val day = today()
    val date = values["date"] ?: day
    val candidate = snapshot?.let { runCatching { purchaseReceiptBody(it, order.s("date"), day, values.toMap() + ("date" to date)) } }
    val signature = candidate?.getOrNull()?.toString()
    val approved = quote?.takeIf { it.first == signature }?.second
    val accepting = snapshot?.s("status") in setOf("open", "partial")
    val locked = sending || unresolved || !vm.canWrite
    fun close() {
        vm.finishToolDraft(scope)
        vm.tool = ""
        vm.toolData = null
        vm.detail = order
        vm.error = ""
    }
    fun refresh(resetQuantities: Boolean) {
        if (resetQuantities) values.keys.filter { it.startsWith("quantity:") }.forEach { values.remove(it) }
        snapshot = null
        quote = null
        reload++
    }

    LaunchedEffect(cid, orderId, reload) {
        if (unresolved || !current()) return@LaunchedEffect
        loadError = ""
        try {
            val result = vm.api.request(vm.api.company(cid, "/purchase-orders/$encodedOrder/receiving")) as JSONObject
            if (current()) {
                require(result.s("order_id") == orderId) { "Refresh this purchase order before receiving." }
                snapshot = result
            }
        } catch (failure: Exception) {
            if (failure is CancellationException) throw failure
            if (current()) {
                if (failure is ApiFailure && failure.status == 401) vm.failure(failure)
                else loadError = failure.message ?: "Could not load order quantities."
            }
        }
    }
    LaunchedEffect(signature, unresolved, reload, vm.canWrite) {
        quoteError = ""
        quote = null
        if (signature == null || unresolved || !vm.canWrite || !current()) return@LaunchedEffect
        delay(200)
        try {
            val result = vm.api.request(vm.api.company(cid, "/purchase-orders/$encodedOrder/receipts/preview"),
                "POST", JSONObject(signature)) as JSONObject
            if (current() && result.decimal("amount").signum() > 0) quote = signature to result.s("amount")
        } catch (failure: Exception) {
            if (failure is CancellationException) throw failure
            if (current()) {
                if (failure is ApiFailure && failure.status == 401) vm.failure(failure)
                else quoteError = failure.message ?: "Could not review the purchase bill total."
            }
        }
    }

    ActionDialog(
        "Receive purchase order",
        vm,
        confirm = if (unresolved) "Retry original receipt" else "Post purchase bill",
        enabled = vm.canWrite && (unresolved || approved != null),
        working = { sending },
        unresolved = { unresolved },
        hasChanges = { values.any { (key, value) -> key != "retry_key" && value.isNotBlank() } },
        onDismiss = ::close,
        confirmationSummary = {
            if (approved != null) DetailValue("Purchase bill total", money(approved))
        },
        onSave = {
            if (!current() || !vm.canWrite) return@ActionDialog
            val body = if (unresolved) submission.body(JSONObject()) else {
                val reviewed = requireNotNull(approved) { "Review the latest purchase bill total." }
                submission.body(JSONObject(signature!!).put("expected_total", reviewed))
            }
            sending = true
            val receipt = try {
                val key = values["retry_key"] ?: draft.key
                vm.api.request(vm.api.company(cid, "/purchase-orders/$encodedOrder/receipts"), "POST", body, key) as JSONObject
            } catch (failure: Exception) {
                if (failure is ApiFailure && failure.status == 409 && failure.code == PO_REVIEW_REQUIRED) {
                    submission.succeeded()
                    values["retry_key"] = UUID.randomUUID().toString()
                    refresh(resetQuantities = true)
                } else submission.failed(failure)
                unresolved = submission.unresolved
                throw failure
            } finally {
                sending = false
            }
            submission.succeeded()
            unresolved = false
            if (current()) {
                close()
                vm.finishConfirmedEntry(if (receipt.optBoolean("posted")) "Stock received on bill ${receipt.s("number")}."
                    else "Bill ${receipt.s("number")} is in the order history as cancelled.")
            }
        },
    ) {
        Text("${order.s("number")} · ${order.s("name")}", style = MaterialTheme.typography.titleMedium)
        if (unresolved) {
            Message("The last receipt may already have posted. Retry the original purchase bill to recover its result.")
        } else if (snapshot == null && loadError.isBlank()) {
            Text("Loading order quantities…")
        } else if (loadError.isNotBlank()) {
            Message(loadError, true)
            OutlinedButton(onClick = { refresh(resetQuantities = false) }) { Text("Retry loading order") }
        } else if (!accepting) {
            Text(purchaseReceivingStatus(snapshot?.s("status").orEmpty()))
            snapshot?.s("reason")?.takeIf { it.isNotBlank() }?.let { Text(it) }
        } else {
            Text("Enter this delivery. Posting creates a supplier bill and adds tracked goods to stock.")
            CompositionLocalProvider(LocalFormEnabled provides !locked) {
                DateField("Bill date", date, { values["date"] = it })
                Field("Supplier bill number", values["number"].orEmpty(), { values["number"] = it }, maximum = 16)
                DateField("Due date", values["due"].orEmpty(), { values["due"] = it }, optional = true)
                Field("Notes", values["notes"].orEmpty(), { values["notes"] = it }, maximum = 500)
                snapshot?.a("lines")?.objects()?.filter { it.decimal("remaining_quantity").signum() > 0 }?.forEach { row ->
                    val index = row.optInt("line_index")
                    val quantity = "quantity:$index"
                    val rate = "rate:$index"
                    Section("${index + 1}. ${row.s("description")}") {
                        Text("Ordered ${row.s("ordered_quantity")} · Received ${row.s("received_quantity")} · ${row.s("remaining_quantity")} ${row.s("unit").ifBlank { "units" }} left",
                            style = MaterialTheme.typography.bodySmall)
                        Text("Order rate ${money(row.s("rate"))} · GST ${row.s("gst_rate")}%")
                        Field("Quantity received", values[quantity].orEmpty(), { values[quantity] = it }, number = true, maximum = 16)
                        if (!values[quantity].isNullOrBlank()) Field("Unit rate override (₹)", values[rate].orEmpty(),
                            { values[rate] = it }, number = true, maximum = 16)
                    }
                }
            }
            val hasQuantity = values.any { (key, value) -> key.startsWith("quantity:") && value.isNotBlank() }
            when {
                quoteError.isNotBlank() -> {
                    Message(quoteError, true)
                    OutlinedButton(enabled = !locked, onClick = { refresh(resetQuantities = false) }) { Text("Refresh order review") }
                }
                signature != null && approved == null -> Text("Checking bill total…")
                hasQuantity && signature == null -> Message(candidate?.exceptionOrNull()?.message ?: "Review the quantities received.", true)
            }
        }
    }
}
