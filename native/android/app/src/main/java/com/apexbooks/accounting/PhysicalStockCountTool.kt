package com.apexbooks.accounting

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.CancellationException
import org.json.JSONObject
import java.util.UUID

@Composable
internal fun PhysicalStockCountTool(vm: AppModel) {
    val scope = "stock_count"
    val cid = vm.companyId
    val toolData = vm.toolData
    val draft = remember(cid) { vm.toolDraft(scope) }
    val current = remember(cid, toolData) { vm.captureReadOwner(scope, toolData) }
    val values = draft.values
    val submission = draft.submission
    var search by remember { mutableStateOf("") }
    var snapshot by remember { mutableStateOf<CountSnapshot?>(null) }
    var snapshotError by remember { mutableStateOf("") }
    var snapshotLoading by remember { mutableStateOf(false) }
    var needsRefresh by remember { mutableStateOf(false) }
    var refresh by remember { mutableIntStateOf(0) }
    var sending by remember { mutableStateOf(false) }
    var unresolved by remember { mutableStateOf(submission.unresolved) }

    val items = remember(vm.records) {
        vm.records.filter {
            val data = it.o("data")
            it.s("kind") == "item" && data.optBoolean("track_stock") &&
                data.optString("item_type", "goods") == "goods"
        }.sortedBy { it.s("name").lowercase() }
    }
    val selectedId = values["item_id"].orEmpty()
    val selected = items.find { it.s("id") == selectedId }
    val counted = values["counted"].orEmpty()
    val reason = values["reason"].orEmpty()
    val unitCost = values["unit_cost"].orEmpty()
    val activeSnapshot = snapshot?.takeIf { it.itemId == selected?.s("id") && !needsRefresh }
    val difference = activeSnapshot?.difference(counted)
    val matches = difference?.signum() == 0
    val increase = difference?.signum() == 1
    val valid = matches || difference != null && reason.isNotBlank() && (!increase || countUnitCost(unitCost) != null)
    val locked = sending || unresolved || !vm.canWrite

    fun clearCount() {
        values["counted"] = ""
        values["unit_cost"] = ""
    }
    fun reload() {
        snapshot = null
        snapshotError = ""
        needsRefresh = false
        clearCount()
        refresh++
    }
    fun close() {
        vm.finishToolDraft(scope)
        vm.tool = ""
        vm.toolData = null
        vm.error = ""
    }

    LaunchedEffect(selectedId, refresh) {
        if (selectedId.isBlank() || unresolved || !current()) return@LaunchedEffect
        snapshot = null
        snapshotError = ""
        snapshotLoading = true
        clearCount()
        try {
            val path = vm.api.company(cid, "/stock/counts/${Uri.encode(selectedId)}")
            val response = vm.api.request(path) as JSONObject
            if (current()) snapshot = CountSnapshot.parse(response, selectedId)
        } catch (failure: Exception) {
            if (failure is CancellationException) throw failure
            if (current()) {
                if (failure is ApiFailure && failure.status == 401) vm.failure(failure)
                else snapshotError = failure.message ?: "Could not load on-hand stock."
            }
        } finally {
            snapshotLoading = false
        }
    }

    ActionDialog(
        title = "Physical stock count",
        vm = vm,
        confirm = when {
            unresolved -> "Retry original count"
            matches -> "Done"
            else -> "Post count"
        },
        enabled = vm.canWrite && (unresolved || valid),
        hasChanges = { counted.isNotBlank() || reason.isNotBlank() || unitCost.isNotBlank() },
        unresolved = { unresolved },
        working = { sending },
        onDismiss = ::close,
        onSave = {
            if (!current() || !vm.canWrite) return@ActionDialog
            if (!unresolved && matches) {
                close()
                return@ActionDialog
            }
            val body = if (unresolved) submission.body(JSONObject()) else submission.body(
                requireNotNull(activeSnapshot) { "Refresh on-hand stock before posting." }.body(counted, reason, unitCost)
            )
            sending = true
            val posted = try {
                val key = values["retry_key"] ?: draft.key
                vm.api.request(vm.api.company(cid, "/stock/counts"), "POST", body, key) as JSONObject
            } catch (failure: Exception) {
                if (stockCountRejected(failure)) {
                    submission.succeeded()
                    values["retry_key"] = UUID.randomUUID().toString()
                    if (failure.message.orEmpty().contains("Refresh on-hand stock", ignoreCase = true)) {
                        needsRefresh = true
                        snapshot = null
                        clearCount()
                    }
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
                val countedQuantity = posted.o("data").o("stock_count").s("counted_quantity")
                vm.finishConfirmedEntry("Count posted for ${posted.s("name")}. On hand: $countedQuantity.")
            }
        },
    ) {
        if (unresolved) {
            Message("The last count may already have posted. Retry the original count to recover the result.")
        }
        if (!vm.canWrite) Message("Posting a count requires owner or editor access.")
        CompositionLocalProvider(LocalFormEnabled provides !locked) {
            Field("Find item by name or barcode", search, { search = it }, maximum = 80)
            val query = search.trim()
            val found = if (query.isEmpty()) items else items.filter {
                it.s("name").contains(query, ignoreCase = true) || it.o("data").s("barcode").contains(query, ignoreCase = true)
            }
            val shown = (listOfNotNull(selected) + found.take(40)).distinctBy { it.s("id") }
            Choice(
                "Tracked item", selectedId,
                listOf("" to "Choose item") + shown.map { item ->
                    val unit = item.o("data").s("unit")
                    item.s("id") to if (unit.isBlank()) item.s("name") else "${item.s("name")} · $unit"
                },
                { id ->
                    if (id != selectedId) {
                        values["item_id"] = id
                        values["reason"] = ""
                        reload()
                    }
                },
                enabled = !locked,
            )
            if (found.size > 40) Text("Showing the first 40 results. Search by barcode or name to narrow the list.", style = MaterialTheme.typography.bodySmall)
            if (items.isEmpty()) Text("Add stock-tracked goods before counting stock.")
            else if (found.isEmpty()) Text("No tracked goods match this search.")
            if (selected != null && !unresolved) {
                when {
                    snapshotLoading -> Text("Loading on-hand stock…")
                    needsRefresh -> Message("Refresh on-hand stock and count this item again.")
                    snapshotError.isNotBlank() -> Message(snapshotError, true)
                    activeSnapshot != null -> Surface(
                        modifier = Modifier.fillMaxWidth(),
                        color = MaterialTheme.colorScheme.primaryContainer,
                        shape = RoundedCornerShape(12.dp),
                    ) {
                        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            val unit = selected.o("data").s("unit").ifBlank { "units" }
                            Text("On hand · ${activeSnapshot.date}", style = MaterialTheme.typography.labelMedium)
                            Text("${activeSnapshot.onHand.toPlainString()} $unit", style = MaterialTheme.typography.titleLarge)
                        }
                    }
                }
                OutlinedButton(enabled = !locked && !snapshotLoading, onClick = ::reload) { Text("Refresh on hand") }
            }
            if (activeSnapshot != null && !unresolved) {
                Field("Counted quantity", counted, { values["counted"] = it }, number = true, maximum = 16)
                if (counted.isNotBlank() && difference == null) {
                    Message("Use a nonnegative quantity with up to three decimal places.", true)
                } else if (difference != null) {
                    Text(if (matches) "Count matches on-hand stock."
                        else "Stock will ${if (increase) "increase" else "decrease"} by ${difference.abs().stripTrailingZeros().toPlainString()}.",
                        style = MaterialTheme.typography.bodyMedium)
                }
                if (increase) Field("Reviewed cost per unit (₹)", unitCost, { values["unit_cost"] = it }, number = true, maximum = 16)
                if (difference != null && !matches) {
                    Field("Reason for the difference", reason, { values["reason"] = it }, multiline = true, maximum = 500)
                }
            }
        }
    }
}
