package com.apexbooks.accounting

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.QrCodeScanner
import androidx.compose.material.icons.outlined.Remove
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import org.json.JSONObject
import java.math.BigDecimal

/** Server rejected a stale quote before writing; the same header is used by the web client. */
internal const val POS_REQUOTE_REQUIRED = "POS_REQUOTE_REQUIRED"

@Composable
fun PosScreen(vm: AppModel) {
    val cid = vm.companyId
    val stamp = vm.workspaceStamp()
    val editor = remember(cid) { vm.saleDraft() }
    var search by remember(cid) { mutableStateOf("") }
    var scanMessage by remember(cid) { mutableStateOf("") }
    var tab by remember(cid) { mutableIntStateOf(0) }
    var saving by remember(cid) { mutableStateOf(false) }
    var retryPending by remember(cid) { mutableStateOf(editor.submission.unresolved) }
    var receipt by remember(cid) { mutableStateOf<JSONObject?>(null) }
    var quote by remember(cid) { mutableStateOf<Pair<String, JSONObject>?>(null) }
    var quoteError by remember(cid) { mutableStateOf("") }
    var revision by remember(cid) { mutableIntStateOf(0) }
    var stock by remember(cid) { mutableStateOf<Map<String, String>?>(null) }
    val context = LocalContext.current
    val locked = saving || retryPending
    val canEdit = vm.canWrite && !locked
    val products = remember(vm.records) {
        vm.records.filter { it.s("kind") == "item" && selectableMaster(it) }
    }
    val strictStock = vm.supports("pos_require_available_stock")
    val splitSupported = vm.supports("pos_split_tender")
    val date = today()
    val previewBody = editor.body().put("date", date)
    val previewData = previewBody.o("data")
    previewData.put("payment_account", "cash")
    previewData.remove("bank_account_id")
    previewData.remove("tender_amount")
    if (strictStock) previewData.put("require_available_stock", true)
    val previewSignature = previewBody.toString()
    val currentQuote = quote?.takeIf { it.first == previewSignature }?.second
    val total = currentQuote?.s("amount")?.toBigDecimalOrNull()
    val payment = editor.get("payment_account")
    val tender = editor.get("tender_amount")
    val bankPart = editor.get("bank_amount")
    val receivingBank = editor.get("bank_account_id")
    var bankConfirmed by remember(cid, payment, receivingBank, bankPart, total, previewSignature) { mutableStateOf(false) }
    val cashDue = total?.let { posCashDue(it, payment, bankPart) }
    val tendered = if (tender.isBlank()) cashDue else posMoneyInput(tender)
    val bankReady = payment == "cash" || bankConfirmed && vm.banks.any { it.s("id") == receivingBank }
    val canCharge = total != null && total > BigDecimal.ZERO && cashDue != null && bankReady &&
        (payment != "split" || splitSupported) &&
        (payment == "bank" || tendered != null && tendered >= cashDue)

    val hasPosStockSummary = vm.supports("pos_stock_summary")
    LaunchedEffect(cid, vm.revision, date, revision, vm.recordsReady, hasPosStockSummary) {
        stock = null
        if (!vm.recordsReady) return@LaunchedEffect
        try {
            val path = if (hasPosStockSummary) "/pos/stock" else "/reports/stock?from_date=$date&to_date=$date"
            val result = vm.api.request(vm.api.company(cid, path)) as JSONObject
            currentCoroutineContext().ensureActive()
            if (vm.inWorkspace(cid, stamp)) {
                stock = result.a("rows").objects().associate { it.s("item_id") to it.s("closing_quantity") }
            }
        } catch (error: Exception) {
            currentCoroutineContext().ensureActive()
            if (error is ApiFailure && error.status == 401 && vm.inWorkspace(cid, stamp)) vm.failure(error)
        }
    }

    LaunchedEffect(cid, previewSignature, retryPending, revision, vm.revision, vm.recordsReady) {
        quote = null
        quoteError = ""
        if (editor.lines.isEmpty() || retryPending || !vm.recordsReady) return@LaunchedEffect
        delay(200)
        try {
            val result = vm.api.request(vm.api.company(cid, "/documents/preview"), "POST", JSONObject(previewSignature)) as JSONObject
            currentCoroutineContext().ensureActive()
            if (vm.inWorkspace(cid, stamp)) quote = previewSignature to result
        } catch (error: Exception) {
            currentCoroutineContext().ensureActive()
            if (!vm.inWorkspace(cid, stamp)) return@LaunchedEffect
            quoteError = error.message ?: "Unable to check the sale total."
            if (error is ApiFailure && error.status == 401) vm.failure(error)
        }
    }

    fun add(item: JSONObject) {
        if (!vm.canWrite || saving || editor.submission.unresolved || !vm.inWorkspace(cid, stamp)) return
        val existing = editor.lines.find { it.get("item_id") == item.s("id") }
        if (existing == null) {
            val line = LineState(regular = vm.regular)
            editor.chooseItem(line, item.s("id"))
            if (line.get("item_id").isBlank()) return
            editor.lines.add(line)
        } else {
            val quantity = existing.get("quantity").toBigDecimalOrNull() ?: BigDecimal.ZERO
            existing.set("quantity", (quantity + BigDecimal.ONE).toPlainString())
        }
        receipt = null
    }

    fun scan(rawValue: String, barcodeOnly: Boolean) {
        if (!vm.canWrite || saving || editor.submission.unresolved || !vm.inWorkspace(cid, stamp)) return
        val value = rawValue.trim()
        if (value.isBlank()) return
        val matches = exactPosMatches(products, value, barcodeOnly)
        val item = matches.singleOrNull()
        if (item == null) {
            search = value
            scanMessage = if (matches.isEmpty()) "No exact product match. Select a product below."
                else "Several products match. Select the one you scanned."
            return
        }
        add(item)
        search = ""
        scanMessage = "${item.s("name")} added"
    }

    fun completeSale() {
        if (!vm.canWrite || saving || !retryPending && !canCharge) return
        if (!retryPending && date != today()) {
            quote = null
            revision++
            return
        }
        saving = true
        vm.task {
            try {
                val candidate = editor.body().put("date", date)
                val data = candidate.o("data")
                if (strictStock) data.put("require_available_stock", true)
                if (strictStock || splitSupported) data.put("expected_total", total?.toPlainString())
                if (vm.supports("pos_register_sessions") && currentQuote != null) {
                    val register = currentQuote.o("data").s("pos_register_session_id")
                    data.put("expected_register_session", register.ifBlank { null } ?: JSONObject.NULL)
                }
                if (payment == "split") {
                    data.put("bank_account_id", editor.get("bank_account_id"))
                    data.put("bank_amount", bankPart)
                }
                if (payment == "bank") data.remove("tender_amount")
                val result = try {
                    vm.api.saveRecord(cid, editor.submission.body(candidate), editor.retryKey)
                } catch (error: Exception) {
                    // Stale quotes are rejected before any write, with a stable code (not message text).
                    // Other POS rejections are definitive too: the server replays committed keys before validating.
                    if (error is ApiFailure && error.code == POS_REQUOTE_REQUIRED) editor.renewRetryKey()
                    else editor.submission.failed(error, definitiveConflict = true)
                    retryPending = editor.submission.unresolved
                    if (!retryPending) revision++
                    throw error
                }
                editor.renewRetryKey()
                retryPending = false
                editor.lines.clear()
                editor.changePartyName("Walk-in customer")
                editor.set("payment_account", "cash")
                editor.set("tender_amount", "")
                editor.set("bank_amount", "")
                if (!vm.inWorkspace(cid, stamp)) return@task
                receipt = result
                scanMessage = ""
                quote = null
                tab = 0
                vm.finishConfirmedEntry("Sale ${result.s("number")} posted.")
                if (vm.inWorkspace(cid, stamp) && vm.page == "pos") vm.notice = ""
            } finally {
                saving = false
            }
        }
    }

    BoxWithConstraints(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 8.dp)) {
        val wide = maxWidth >= 760.dp
        val reviewCart = !wide && tab == 0 && !retryPending
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (wide) PrimaryTabRow(if (tab == 2) 1 else 0) {
                Tab(tab != 2, onClick = { tab = 0 }, text = { Text("New sale") })
                Tab(tab == 2, onClick = { tab = 2 }, text = { Text("Receipts") })
            } else PrimaryTabRow(tab) {
                Tab(tab == 0, onClick = { tab = 0 }, text = { Text("Products") })
                Tab(tab == 1, onClick = { tab = 1 }, text = { Text("Cart (${editor.lines.size})") })
                Tab(tab == 2, onClick = { tab = 2 }, text = { Text("Receipts") })
            }
            if (tab == 2) {
                PosHistory(vm, Modifier.weight(1f).fillMaxWidth())
            } else {
                val catalog: @Composable (Modifier) -> Unit = { modifier ->
                    PosCatalog(products, stock, search, scanMessage, canEdit, !locked, modifier,
                        setup = vm.inventorySetup,
                        onSearch = { search = it; scanMessage = "" },
                        onSubmitSearch = { scan(search, false) },
                        onCamera = {
                            GmsBarcodeScanning.getClient(context).startScan()
                                .addOnSuccessListener { value -> value.rawValue?.let { scan(it, true) } }
                                .addOnFailureListener {
                                    if (vm.inWorkspace(cid, stamp)) scanMessage = "Camera scan unavailable. Type the barcode or use a handheld scanner."
                                }
                        },
                        onAdd = ::add)
                }
                if (wide) Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    catalog(Modifier.weight(1f).fillMaxHeight())
                    PosCart(vm, editor, stock, splitSupported, canEdit, bankConfirmed, { bankConfirmed = it },
                        Modifier.weight(1f).fillMaxHeight())
                } else if (tab == 0) {
                    catalog(Modifier.weight(1f).fillMaxWidth())
                } else {
                    PosCart(vm, editor, stock, splitSupported, canEdit, bankConfirmed, { bankConfirmed = it },
                        Modifier.weight(1f).fillMaxWidth())
                }

                if (receipt != null && editor.lines.isEmpty()) {
                    PosReceipt(vm, receipt!!, onDismiss = { receipt = null })
                } else {
                    PosCheckout(total, cashDue, tendered, payment, quoteError, saving, retryPending,
                        hasItems = editor.lines.isNotEmpty(),
                        reviewCart = reviewCart,
                        bankConfirmationNeeded = payment != "cash" && !bankConfirmed,
                        enabled = vm.canWrite && !saving && (retryPending || if (reviewCart) editor.lines.isNotEmpty() else canCharge),
                        onRefresh = { revision++ },
                        onCheckout = { if (reviewCart) tab = 1 else completeSale() })
                }
            }
        }
    }
}

@Composable
private fun PosCatalog(
    products: List<JSONObject>, stock: Map<String, String>?, search: String, scanMessage: String,
    enabled: Boolean, browsingEnabled: Boolean, modifier: Modifier, onSearch: (String) -> Unit, onSubmitSearch: () -> Unit,
    onCamera: () -> Unit, onAdd: (JSONObject) -> Unit, setup: JSONObject? = null,
) {
    val keyword = search.trim()
    val visible = products.filter { item -> InventoryText.searchText(item, setup).contains(keyword, ignoreCase = true) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        OutlinedTextField(search, onSearch, label = { Text("Search or scan barcode") }, enabled = browsingEnabled,
            leadingIcon = { IconButton(onClick = onCamera, enabled = enabled) {
                Icon(Icons.Outlined.QrCodeScanner, "Scan barcode with camera")
            } },
            trailingIcon = if (search.isNotEmpty()) ({ IconButton(onClick = { onSearch("") }, enabled = browsingEnabled) {
                Icon(Icons.Outlined.Close, "Clear product search")
            } }) else null,
            modifier = Modifier.fillMaxWidth().onPreviewKeyEvent { event ->
                if (enabled && event.key == Key.Enter) {
                    if (event.type == KeyEventType.KeyUp) onSubmitSearch()
                    true
                } else false
            },
            singleLine = true, keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { onSubmitSearch() }))
        if (scanMessage.isNotBlank()) Text(scanMessage, style = MaterialTheme.typography.bodyMedium)
        if (visible.isEmpty()) Text(if (keyword.isBlank()) "No products in this company." else "No products match this search.")
        LazyVerticalGrid(GridCells.Adaptive(144.dp), Modifier.weight(1f),
            horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(visible, key = { it.s("id") }) { item ->
                val details = item.o("data")
                Card(onClick = { onAdd(item) }, enabled = enabled, border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.fillMaxWidth().heightIn(min = 112.dp).padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        details.s("image_thumbnail").takeIf(String::isNotBlank)?.let { url ->
                            DataImage(url, Modifier.fillMaxWidth().height(70.dp))
                        }
                        Text(item.s("name"), style = MaterialTheme.typography.titleSmall,
                            maxLines = 2, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold)
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text(money(details.s("sale_rate")), modifier = Modifier.weight(1f),
                                style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.SemiBold)
                            if (enabled) Icon(Icons.Outlined.Add, "Add to cart",
                                Modifier.size(20.dp), tint = MaterialTheme.colorScheme.primary)
                        }
                        InventoryText.locationNames(setup, InventoryText.locationIds(details)).takeIf { it.isNotEmpty() }?.let {
                            Text("📍 " + it.joinToString(" · "), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                        if (details.optBoolean("track_stock")) PosBookStock(stock?.get(item.s("id")))
                    }
                }
            }
        }
    }
}

@Composable
private fun PosBookStock(quantity: String?) {
    val value = quantity?.toBigDecimalOrNull()
    Text(if (value == null) "Book stock unavailable" else "${value.stripTrailingZeros().toPlainString()} in stock",
        color = if (value != null && value.signum() <= 0) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.bodySmall)
}

@Composable
private fun PosCart(
    vm: AppModel, editor: EntryEditor, stock: Map<String, String>?, splitSupported: Boolean,
    enabled: Boolean, bankConfirmed: Boolean, onConfirmBank: (Boolean) -> Unit, modifier: Modifier,
) {
    var customerOpen by remember { mutableStateOf(false) }
    LazyColumn(modifier, verticalArrangement = Arrangement.spacedBy(12.dp),
        contentPadding = PaddingValues(bottom = 8.dp)) {
        if (editor.lines.isEmpty()) item {
            Section("Cart") { Text("Choose a product or scan its barcode to add it to the cart.") }
        }
        items(editor.lines, key = { it.uiKey }) { line ->
            PosCartLine(line, stock?.get(line.get("item_id")), vm.regular, enabled, onRemove = { editor.lines.remove(line) })
        }
        if (editor.lines.isNotEmpty()) item {
            Section("Payment") {
                val method = editor.get("payment_account")
                val options = listOf("cash" to "Cash", "bank" to "Bank / UPI / card")
                Choice("Payment method", method, if (splitSupported || method == "split") options + ("split" to "Split cash and bank") else options,
                    { next -> editor.set("payment_account", next); editor.set("tender_amount", ""); editor.set("bank_amount", "") }, enabled = enabled)
                if (method != "cash") Choice("Receiving bank", editor.get("bank_account_id"),
                    vm.banks.map { it.s("id") to it.s("name") }, { editor.set("bank_account_id", it) }, enabled = enabled)
                if (method == "split") Field("Bank amount (₹)", editor.get("bank_amount"), { editor.set("bank_amount", it) },
                    number = true, readOnly = !enabled)
                if (method != "bank") Field("Cash tendered (₹)", editor.get("tender_amount"), { editor.set("tender_amount", it) },
                    number = true, readOnly = !enabled)
                if (method != "cash") Toggle("Bank / UPI / card payment received", bankConfirmed, onConfirmBank, enabled = enabled)
            }
        }
        if (editor.lines.isNotEmpty()) item {
            Section("Customer and billing") {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(editor.get("name"), Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
                    TextButton(onClick = { customerOpen = !customerOpen }) {
                        Text(if (customerOpen) "Hide details" else "Edit customer")
                    }
                }
                if (customerOpen) {
                    Choice("Saved customer", editor.get("party_id"),
                        listOf("" to "Walk-in / entered customer") + editor.parties().map { it.s("id") to it.s("name") },
                        { editor.chooseParty(it) }, enabled = enabled)
                    Field("Customer name", editor.get("name"), editor::changePartyName, readOnly = !enabled, maximum = 120)
                    Field("Address", editor.get("party_address"), { editor.set("party_address", it) },
                        readOnly = !enabled, multiline = true, maximum = 1000)
                    Field("Phone", editor.get("party_phone"), { editor.set("party_phone", it) }, readOnly = !enabled, maximum = 32)
                    if (vm.regular) {
                        Field("GSTIN", editor.get("party_gstin"), {
                            editor.set("party_gstin", it.uppercase())
                            if (it.length >= 2) editor.set("place_of_supply", it.take(2))
                        }, readOnly = !enabled, maximum = 15)
                        Field("Place of supply (state code)", editor.get("place_of_supply"), { editor.set("place_of_supply", it) },
                            readOnly = !enabled, maximum = 2)
                    }
                    Toggle("Round total to nearest rupee", editor.flag("round_total"), { editor.set("round_total", it.toString()) }, enabled = enabled)
                }
            }
        }
    }
}

@Composable
private fun PosCartLine(line: LineState, stock: String?, regular: Boolean, enabled: Boolean, onRemove: () -> Unit) {
    var options by remember { mutableStateOf(false) }
    Section(line.get("description")) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            IconButton(enabled = enabled, onClick = {
                val quantity = line.get("quantity").toBigDecimalOrNull() ?: BigDecimal.ONE
                if (quantity > BigDecimal.ONE) line.set("quantity", (quantity - BigDecimal.ONE).toPlainString()) else onRemove()
            }) { Icon(Icons.Outlined.Remove, "Decrease quantity") }
            Field("Quantity", line.get("quantity"), { line.set("quantity", it) }, Modifier.weight(1f), number = true, readOnly = !enabled)
            IconButton(enabled = enabled, onClick = {
                val quantity = line.get("quantity").toBigDecimalOrNull() ?: BigDecimal.ZERO
                line.set("quantity", (quantity + BigDecimal.ONE).toPlainString())
            }) { Icon(Icons.Outlined.Add, "Increase quantity") }
            IconButton(enabled = enabled, onClick = onRemove) { Icon(Icons.Outlined.DeleteOutline, "Remove item") }
        }
        Text("${money(line.get("rate"))} per ${line.get("unit").ifBlank { "unit" }}",
            style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
        if (stock != null) PosBookStock(stock)
        TextButton(onClick = { options = !options }) { Text(if (options) "Hide price details" else "Price, discount and tax") }
        if (options) {
            Field("Rate (₹)", line.get("rate"), { line.set("rate", it) }, number = true, readOnly = !enabled)
            Choice("Line discount", line.discountMode, listOf("percent" to "Percentage (%)", "amount" to "Fixed amount (₹)"),
                line::chooseDiscountMode, enabled = enabled)
            val fixed = line.discountMode == "amount"
            val discount = if (fixed) "discount_amount" else "discount_percent"
            Field(if (fixed) "Discount (₹)" else "Discount (%)", line.get(discount), { line.set(discount, it) },
                number = true, readOnly = !enabled)
            if (regular) {
                Toggle("Price includes GST", line.get("price_includes_tax") == "true", { line.set("price_includes_tax", it.toString()) }, enabled = enabled)
                Choice("Supply classification", line.get("tax_treatment"), supplyChoices, {
                    line.set("tax_treatment", it)
                    if (it != "taxable") line.set("gst_rate", "0")
                }, enabled = enabled)
                Field("GST rate (%)", line.get("gst_rate"), { line.set("gst_rate", it) }, number = true, readOnly = !enabled)
            }
        }
    }
}

@Composable
private fun PosCheckout(
    total: BigDecimal?, cashDue: BigDecimal?, tendered: BigDecimal?, payment: String, quoteError: String,
    saving: Boolean, retryPending: Boolean, hasItems: Boolean, reviewCart: Boolean, enabled: Boolean,
    bankConfirmationNeeded: Boolean, onRefresh: () -> Unit, onCheckout: () -> Unit,
) {
    Surface(tonalElevation = 2.dp, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Total payable", style = MaterialTheme.typography.titleMedium)
                Text(total?.let { money(it) } ?: "—", style = MaterialTheme.typography.headlineSmall,
                    color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold)
            }
            when {
                retryPending -> Text("Sale confirmation is pending. Retry the original sale.", color = MaterialTheme.colorScheme.error)
                quoteError.isNotBlank() -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(quoteError, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    TextButton(onClick = onRefresh) { Text("Refresh total") }
                }
                hasItems && total == null -> Text("Checking total…", style = MaterialTheme.typography.bodySmall)
                payment == "split" && total != null && cashDue == null ->
                    Text("Enter a bank amount below the sale total.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                payment != "bank" && cashDue != null -> {
                    val change = tendered?.minus(cashDue)
                    val summary = when {
                        change == null -> "Enter a cash amount with up to two decimal places."
                        change.signum() < 0 -> "Still due ${money(change.abs())}"
                        else -> "Cash due ${money(cashDue)}  ·  Change ${money(change)}"
                    }
                    Text(summary, style = MaterialTheme.typography.bodyMedium)
                }
            }
            if (!reviewCart && !retryPending && bankConfirmationNeeded && total != null) {
                Text("Confirm the bank payment in Payment.", style = MaterialTheme.typography.bodySmall)
            }
            Button(onClick = onCheckout, enabled = enabled, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                Text(when {
                    saving -> "Posting sale…"
                    retryPending -> "Retry original sale"
                    reviewCart -> "Review cart"
                    else -> "Complete sale"
                })
            }
        }
    }
}

@Composable
private fun PosReceipt(vm: AppModel, receipt: JSONObject, onDismiss: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.fillMaxWidth().padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Sale complete", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text("${receipt.s("number")} · ${money(receipt.s("amount"))}", style = MaterialTheme.typography.bodyLarge)
                }
                IconButton(onClick = onDismiss) { Icon(Icons.Outlined.Close, "Dismiss receipt") }
            }
            val change = receipt.o("data").decimal("change_amount")
            if (change.signum() > 0) Text("Change ${money(change)}", style = MaterialTheme.typography.bodyMedium)
            Button(onClick = { vm.documentPdf(receipt) }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                Icon(Icons.Outlined.Description, null)
                Spacer(Modifier.width(8.dp))
                Text("View or print receipt")
            }
        }
    }
}

@Composable
private fun PosHistory(vm: AppModel, modifier: Modifier) {
    var search by remember { mutableStateOf("") }
    val sales = vm.records.filter {
        it.s("kind") == "pos" && "${it.s("name")} ${it.s("number")} ${it.s("date")}".contains(search.trim(), true)
    }.sortedWith(compareByDescending<JSONObject> { it.s("date") }.thenByDescending { it.s("number") })
    LazyColumn(modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            OutlinedTextField(search, { search = it }, label = { Text("Search receipt number, customer or date") },
                modifier = Modifier.fillMaxWidth(), singleLine = true)
        }
        if (sales.isEmpty()) item { Section { Text("No receipts match this search.") } }
        items(sales, key = { it.s("id") }) { RecordCard(vm, it) }
    }
}
