@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import org.json.JSONObject

@Composable fun EntryScreen(editor: EntryEditor) {
    val vm = editor.vm
    var step by rememberSaveable(editor.retryKey) { mutableIntStateOf(0) }
    var discard by remember { mutableStateOf(false) }
    var stepError by remember { mutableStateOf("") }
    val scroll = rememberScrollState()
    val idle = !editor.saving && !editor.scanning && !editor.sourceLoading
    val serialized = if (editor.document) editor.body().toString() else ""
    val previewReady = editor.lines.isNotEmpty() && editor.lines.none { it.get("description").isBlank() || it.get("quantity").isBlank() || it.get("rate").isBlank() }
    val previewStatus = when {
        !previewReady -> "Add item details"
        editor.previewError.isNotBlank() -> "Total unavailable"
        else -> "Calculating…"
    }
    LaunchedEffect(serialized) {
        if (!editor.document) return@LaunchedEffect
        editor.preview = null; editor.previewError = ""
        if (!previewReady) return@LaunchedEffect
        delay(350)
        try { editor.preview = vm.api.request(vm.api.company(editor.companyId, "/documents/preview"), "POST", JSONObject(serialized)) as JSONObject }
        catch (e: Exception) { currentCoroutineContext().ensureActive(); editor.previewError = e.message ?: "Preview is unavailable."; if (e is ApiFailure && e.status == 401) vm.failure(e) }
    }
    LaunchedEffect(step) { scroll.scrollTo(0); stepError = "" }
    fun close() { if (idle) { if (editor.retryPending) { discard = false; stepError = "The previous save may already have posted. Retry original save to recover its outcome before closing; do not create a replacement entry." } else if (editor.changed()) discard = true else { vm.error = ""; vm.notice = ""; vm.editor = null } } }
    fun next() {
        val issue = entryStepIssue(step, editor.get("name"), editor.get("date"), editor.lines.map { Triple(it.get("description"), it.get("quantity"), it.get("rate")) })
        if (issue != null) stepError = issue else { stepError = ""; step++ }
    }
    fun change(key: String, value: String) = editor.set(key, value)
    Dialog(onDismissRequest = { if (editor.document && step > 0 && idle) step-- else close() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxSize().safeDrawingPadding().imePadding(), color = MaterialTheme.colorScheme.background) {
            Scaffold(containerColor = MaterialTheme.colorScheme.background, topBar = { Column {
                TopAppBar(title = { Column {
                    Text(if (editor.previous != null) "Edit ${editor.previous.s("number").ifBlank { editor.previous.s("name") }}" else "New ${friendly(editor.kind)}", maxLines = 1, style = MaterialTheme.typography.titleLarge)
                    Text(vm.company.s("name"), style = MaterialTheme.typography.labelMedium, maxLines = 1, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } }, navigationIcon = { IconButton(enabled = idle, onClick = { close() }) { Icon(Icons.Outlined.Close, "Close entry") } })
                if (editor.document) Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("Details", "Items", "Review").forEachIndexed { index, title ->
                        Surface(Modifier.weight(1f).clickable(enabled = idle && index < step) { step = index }, shape = RoundedCornerShape(12.dp), color = if (index == step) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface) {
                            Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                if (index < step) Icon(Icons.Outlined.CheckCircle, null, Modifier.size(16.dp), tint = ApexGreen) else Text("${index + 1}", color = ApexGreen, fontWeight = FontWeight.Bold)
                                Text(title, style = MaterialTheme.typography.labelLarge, fontWeight = if (index == step) FontWeight.Bold else FontWeight.Normal)
                            }
                        }
                    }
                }
            } }, bottomBar = { Surface(shadowElevation = 8.dp) {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (vm.error.isNotBlank()) Message(vm.error, true) { vm.error = "" }
                    if (stepError.isNotBlank()) Text(stepError, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
                    if (editor.document) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Text("Total", style = MaterialTheme.typography.labelLarge)
                            Text(editor.preview?.takeIf { previewReady }?.let { money(it.s("amount")) } ?: previewStatus, style = MaterialTheme.typography.titleLarge, color = ApexGreen, fontWeight = FontWeight.Bold)
                        }
                        if (editor.previewError.isNotBlank()) Text(editor.previewError, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        if (editor.document && step > 0) OutlinedButton(enabled = idle, onClick = { step-- }, modifier = Modifier.weight(1f)) { Text("Back") }
                        if (editor.document && step < 2) Button(enabled = idle, onClick = { next() }, modifier = Modifier.weight(1f)) { Text(if (step == 0) "Next: add items" else "Review document"); Icon(Icons.Outlined.ChevronRight, null) }
                        else {
                            if (!editor.document && editor.canSaveAndNew) OutlinedButton(onClick = { editor.save(true) }, enabled = idle && vm.busy == 0, modifier = Modifier.weight(1f)) { Text("Save & new") }
                            Button(onClick = { editor.save() }, enabled = idle && vm.busy == 0 && (editor.retryPending || !editor.document || editor.preview != null), modifier = Modifier.weight(1f)) {
                                if (editor.saving) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                                else Text(if(editor.retryPending) "Retry original save" else if (editor.sourceLoading) "Loading source…" else if (editor.previous != null) "Save changes" else "Save ${when (editor.kind) { "sales_invoice" -> "invoice"; "purchase_bill" -> "bill"; "payment_in" -> "receipt"; "payment_out" -> "payment"; else -> "record" }}")
                            }
                        }
                    }
                }
            } }) { padding -> Column(Modifier.padding(padding).fillMaxSize().verticalScroll(scroll).padding(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                if (editor.scanning) Message("Reading your purchase image…")
                if(editor.retryPending) Message("The previous save has an unknown outcome. Retry original save submits the original values, not subsequent edits. Resolve it before creating another document.")
                if (editor.ocrTotal.isNotBlank()) Message("Scanned total ${money(editor.ocrTotal)}. Review the extracted details and items before saving.")
                if (editor.master) MasterFields(editor)
                else {
                    if (!editor.document || step == 0) {
                        if (editor.kind == "purchase_bill") Section("Scan a supplier bill") {
                            Text("Use a photo to fill the draft, then review it here.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                OutlinedButton(enabled = idle, onClick = { vm.files.pick(arrayOf("image/*"), editor::scan) }, modifier = Modifier.weight(1f)) { Icon(Icons.Outlined.UploadFile, null, Modifier.size(18.dp)); Text("Upload") }
                                FilledTonalButton(enabled = idle, onClick = { vm.files.capture(editor::scan) }, modifier = Modifier.weight(1f)) { Icon(Icons.Outlined.PhotoCamera, null, Modifier.size(18.dp)); Text("Camera") }
                            }
                        }
                        Section(if (editor.purchase) "Supplier details" else "Customer details") {
                            if (editor.kind in setOf("credit_note", "debit_note")) Choice("Original invoice / bill", editor.get("applied_to"), listOf("" to "Choose source") + editor.targets().map { it.s("id") to "${it.s("number")} · ${it.s("name")}" }, editor::chooseSource)
                            Choice("Saved party", editor.get("party_id"), listOf("" to "Enter manually") + editor.parties().map { it.s("id") to it.s("name") }, editor::chooseParty)
                            Field(if (editor.kind == "expense") "Supplier / expense description" else if (editor.purchase) "Supplier name" else "Customer name", editor.get("name"), editor::changePartyName, maximum = 120)
                            if (editor.document) Field("Phone · optional", editor.get("party_phone"), { change("party_phone", it) }, maximum = 32)
                        }
                        Section("Document details") {
                            DateField("Date", editor.get("date"), { change("date", it) })
                            if (editor.kind in setOf("sales_invoice", "purchase_bill")) Column { DateField("Due date · optional", editor.get("due_date"), { change("due_date", it) }, optional = true);PartyTermsSuggestion(editor) }
                            Field("Reference · automatic when blank", editor.get("number"), { change("number", it) }, maximum = 16)
                            if (editor.payment) Field("Amount (₹)", editor.get("amount"), { change("amount", it) }, number = true)
                        }
                        if (editor.document) {
                            if (editor.regular || editor.purchase) FoldSection("GST & place of supply") {
                                Field("Party GSTIN", editor.get("party_gstin"), { change("party_gstin", it.uppercase()); if (it.length >= 2) change(if (editor.purchase) "supplier_state" else "place_of_supply", it.take(2)) }, maximum = 15)
                                if (editor.purchase) Field("Supplier state code", editor.get("supplier_state"), { change("supplier_state", it) }, maximum = 2)
                                Field("Place of supply · state code", editor.get("place_of_supply"), { change("place_of_supply", it) }, maximum = 2)
                            }
                            FoldSection("Billing & shipping addresses") {
                                Field("Billing address", editor.get("party_address"), { change("party_address", it) }, multiline = true, maximum = 1000)
                                Field("Shipping address", editor.get("shipping_address"), { change("shipping_address", it) }, multiline = true, maximum = 1000)
                            }
                        }
                    }
                    if (editor.document && step == 1) {
                        Heading("Items & services", "${editor.lines.size} item lines · tap a line to edit")
                        editor.lines.forEachIndexed { index, line -> key(line.uiKey) { CollapsibleLine(editor, line, index) } }
                        OutlinedButton(onClick = { if (editor.lines.size < 100) editor.lines.add(LineState(regular = editor.regular)) }, enabled = idle, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Outlined.Add, null); Text("Add item or service") }
                    }
                    if (editor.document && step == 2) {
                        Heading("Review & save", "Check the amounts and tax before posting.")
                        Section("Document summary") {
                            DetailValue(if (editor.purchase) "Supplier" else "Customer", editor.get("name"))
                            DetailValue("Date", editor.get("date"))
                            if (editor.get("due_date").isNotBlank()) DetailValue("Due date", editor.get("due_date"))
                            editor.lines.forEachIndexed { index, line ->
                                val calculated = editor.preview?.o("data")?.a("lines")?.optJSONObject(index)
                                DetailValue(line.get("description") + " × " + line.get("quantity"), calculated?.let { money(it.decimal("taxable") + it.decimal("tax")) } ?: previewStatus)
                            }
                            HorizontalDivider()
                            val totals = editor.preview?.o("data")
                            if (totals != null) {
                                for ((key, label) in listOf("taxable" to "Taxable amount", "cgst" to "CGST", "sgst" to "SGST", "igst" to "IGST", "supplier_tax" to "Supplier GST", "round_off" to "Round off")) if (totals.has(key) && (key == "taxable" || totals.decimal(key).signum() != 0)) DetailValue(label, money(totals.s(key)))
                            }
                            DetailValue("Total", editor.preview?.takeIf { previewReady }?.let { money(it.s("amount")) } ?: previewStatus)
                        }
                        if(editor.previous==null&&editor.kind in setOf("sales_invoice","estimate","proforma","sales_order")){
                            if(editor.get("party_id").isBlank())Text("Select a saved customer to check their credit limit.",style=MaterialTheme.typography.bodySmall)
                            else editor.preview?.s("amount")?.takeIf{it.isNotBlank()}?.let{CustomerCreditStatus(vm,editor.get("party_id"),editor.get("date"),it)}
                        }
                        if(editor.hasFixedLinkedReturn)Section("Return discount review"){Text("Fixed discounts are retained from the source, not automatically prorated for returned quantities. Review and adjust each amount explicitly.",style=MaterialTheme.typography.bodySmall);Toggle("I reviewed the fixed discount against returned quantities",!editor.fixedReturnReviewNeeded,{editor.acknowledgeReturnDiscount(it)})}
                        FoldSection("Discounts, notes & terms") {
                            Field("Document discount (%)", editor.get("document_discount_percent"), { change("document_discount_percent", it) }, number = true)
                            Toggle("Round total to nearest rupee", editor.flag("round_total"), { change("round_total", it.toString()) })
                            if (editor.kind in setOf("credit_note", "debit_note")) Toggle("Return stock with this note", editor.flag("return_stock"), { change("return_stock", it.toString()) })
                            if (editor.kind == "expense") Field("Expense category", editor.get("category"), { change("category", it) }, maximum = 100)
                            Field("Notes", editor.get("notes"), { change("notes", it) }, multiline = true, maximum = 4000)
                            Field("Terms and conditions", editor.get("terms"), { change("terms", it) }, multiline = true, maximum = 8000)
                        }
                    }
                    if (editor.document && step == 2 && editor.canPayNow) Section(if (editor.kind == "sales_invoice") "Received now" else "Paid now") {
                        Toggle(if (editor.kind == "sales_invoice") "Record the payment received with this invoice" else "Record the payment made with this bill", editor.flag("pay_now"), { change("pay_now", it.toString()) })
                        if (editor.flag("pay_now")) {
                            Field("Amount (₹)", editor.get("pay_amount"), { change("pay_amount", it) }, number = true)
                            editor.preview?.takeIf { previewReady }?.s("amount")?.takeIf { it.isNotBlank() }?.let { total ->
                                TextButton(onClick = { change("pay_amount", total) }) { Text("Full amount · ${money(total)}") }
                                val paid = editor.get("pay_amount").toBigDecimalOrNull()
                                if (paid != null && paid.signum() > 0) Text("Balance after this: ${money((total.toBigDecimalOrNull() ?: java.math.BigDecimal.ZERO).subtract(paid).max(java.math.BigDecimal.ZERO))}", style = MaterialTheme.typography.bodySmall)
                            }
                            Choice(if (editor.kind == "sales_invoice") "Received in" else "Paid from", editor.get("pay_account").ifBlank { "cash" }, listOf("cash" to "Cash", "bank" to "Bank / UPI / card"), { change("pay_account", it) })
                            if (editor.get("pay_account") == "bank") Choice("Bank", editor.get("pay_bank").ifBlank { "default" }, vm.banks.map { it.s("id") to it.s("name") }, { change("pay_bank", it) })
                        }
                    }
                    if (editor.document && step == 2 && editor.canSaveAndNew) TextButton(enabled = idle && vm.busy == 0 && editor.preview != null, onClick = { editor.save(true) }, modifier = Modifier.fillMaxWidth()) { Text("Save & create another") }
                    if (editor.payment) PaymentFields(editor)
                    if ((!editor.document || step == 2) && editor.kind in setOf("payment_in", "payment_out", "expense", "pos")) Section("Payment account") {
                        Choice("Paid through", editor.get("payment_account"), listOf("cash" to "Cash", "bank" to "Bank / UPI / card"), { change("payment_account", it) })
                        if (editor.get("payment_account") == "bank") Choice("Bank", editor.get("bank_account_id"), vm.banks.map { it.s("id") to it.s("name") }, { change("bank_account_id", it) })
                        if (editor.kind == "pos" && editor.get("payment_account") == "cash") Field("Cash tendered (₹)", editor.get("tender_amount"), { change("tender_amount", it) }, number = true)
                    }
                }
                Spacer(Modifier.height(16.dp))
            } }
        }
    }
    if (discard && !editor.retryPending) AlertDialog(onDismissRequest = { discard = false }, title = { Text("Discard unsaved changes?") }, text = { Text("This draft has not been saved.") }, confirmButton = { TextButton(onClick = { discard = false; vm.error = ""; vm.notice = ""; vm.editor = null }) { Text("Discard draft") } }, dismissButton = { TextButton(onClick = { discard = false }) { Text("Keep editing") } })
}

@Composable private fun CollapsibleLine(editor: EntryEditor, line: LineState, index: Int) {
    var expanded by rememberSaveable(line.uiKey) { mutableStateOf(line.get("description").isBlank()) }
    if (expanded) {
        Column {
            TextButton(onClick = { expanded = false }) { Text("Collapse item ${index + 1}"); Icon(Icons.Outlined.ExpandLess, null) }
            LineFields(editor, line, index)
        }
    } else Card(onClick = { expanded = true }, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), shape = RoundedCornerShape(20.dp)) {
        Row(Modifier.fillMaxWidth().padding(18.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Inventory2, null, tint = ApexGreen)
            Column(Modifier.weight(1f)) { Text(line.get("description").ifBlank { "Item ${index + 1}" }, fontWeight = FontWeight.SemiBold); Text("${line.get("quantity")} ${line.get("unit")} × ${money(line.get("rate"))}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            Icon(Icons.Outlined.Edit, "Edit item ${index + 1}")
        }
    }
}

@Composable private fun MasterFields(editor:EntryEditor){val vm=editor.vm;Section(if(editor.kind=="party")"Party details"else"Item details"){Field("Name",editor.get("name"),{editor.set("name",it)},readOnly=editor.previous!=null,maximum=120);if(ApiCapabilities.masterFields.values.any{!vm.supports(it)})FeatureUpgradeHint(vm);if(vm.supports("master_lifecycle"))Toggle("Active for new transactions",editor.flag("is_active"),{editor.set("is_active",it.toString())});Text("Inactive masters stay in history but cannot be selected for new transactions. Reactivate here when needed.",style=MaterialTheme.typography.bodySmall);if(editor.kind=="party"){
    Choice("Party type",editor.get("party_type"),listOf("both" to "Customer and supplier","customer" to "Customer","supplier" to "Supplier"),{editor.set("party_type",it)});for((key,label)in listOf("gstin" to "GSTIN","phone" to "Phone","email" to "Email","address" to "Address","shipping_address" to "Default shipping address").filter{it.first!="shipping_address"||vm.supports("party_shipping_address")})Field(label,editor.get(key),{editor.set(key,if(key=="gstin")it.uppercase()else it)},multiline=key in setOf("address","shipping_address"),maximum=if(key=="gstin")15 else if(key in setOf("address","shipping_address"))500 else if(key=="phone")32 else 254)
        if(vm.supports("party_credit_limits"))Field("Customer credit limit · optional (₹)",editor.get("credit_limit"),{editor.set("credit_limit",it)},number=true,maximum=18);Text("Blank disables warnings; zero warns for any positive exposure. Warnings never block a sale.",style=MaterialTheme.typography.bodySmall)
        if(vm.supports("party_payment_terms"))Field("Payment terms · days (optional)",editor.get("payment_terms_days"),{editor.set("payment_terms_days",it)},number=true,maximum=4);Text("0 means due on the document date. Blank disables suggestions; saved document dates are never changed automatically.",style=MaterialTheme.typography.bodySmall)
    }else{
        DataImage(editor.get("image_data_url"),Modifier.fillMaxWidth().height(130.dp));Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){OutlinedButton(onClick={vm.files.pick(arrayOf("image/*")){uri->vm.task{editor.set("image_data_url",vm.files.image(uri));editor.set("image_thumbnail",vm.files.image(uri,140,15000))}}}){Text("Upload item image")};TextButton(onClick={editor.set("image_data_url","");editor.set("image_thumbnail","")}){Text("Remove")}}
        Choice("Type",editor.get("item_type"),listOf("goods" to "Goods","services" to "Services"),{editor.set("item_type",it)});Toggle("Track stock",editor.flag("track_stock"),{editor.set("track_stock",it.toString())},enabled=editor.previous==null);for((key,label)in listOf("hsn" to "HSN / SAC","unit" to "Unit","barcode" to "Barcode","sale_rate" to "Sale price (₹)","purchase_rate" to "Purchase price (₹)","gst_rate" to "GST rate (%)"))Field(label,editor.get(key),{editor.set(key,it)},number=key.endsWith("rate"),maximum=if(key=="barcode")80 else 24);Choice("Supply classification",editor.get("tax_treatment"),supplyChoices,{editor.set("tax_treatment",it)})
        if(vm.supports("low_stock_reorder")&&((editor.flag("track_stock")&&editor.get("item_type")=="goods")||editor.get("low_stock_threshold").isNotBlank())){Field("Low-stock threshold · optional",editor.get("low_stock_threshold"),{editor.set("low_stock_threshold",it)},number=true,maximum=18);Text("Blank disables alerts. Items at or below this quantity appear in Reorder review; no purchase is posted automatically.",style=MaterialTheme.typography.bodySmall)}
    }}}
val supplyChoices=listOf("taxable" to "Taxable","nil_rated" to "Nil rated","exempt" to "Exempt","non_gst" to "Non-GST")
@Composable private fun LineFields(editor:EntryEditor,line:LineState,index:Int){
    Section("Item ${index+1}"){
        val calculated=editor.preview?.o("data")?.a("lines")?.optJSONObject(index)
        if(calculated!=null){val amount=(calculated.s("taxable").toBigDecimalOrNull()?:java.math.BigDecimal.ZERO)+(calculated.s("tax").toBigDecimalOrNull()?:java.math.BigDecimal.ZERO);Text(money(amount),style=MaterialTheme.typography.titleMedium,color=ApexGreen)}
        val products=editor.items(line)
        Choice("Item / service",line.get("item_id"),listOf("" to "Enter a description")+products.map{it.s("id") to it.s("name")},{if(it.isBlank())line.set("item_id","")else editor.chooseItem(line,it)})
        ItemPriceSuggestion(editor,line)
        if(line.get("item_id").isBlank())Field("Description",line.get("description"),{line.set("description",it)},maximum=200)
        else Text(if(line.importedFromOcr)"Product linked · scanned rate and GST kept" else "Product selected · ${line.get("unit")}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){
            Field("Quantity",line.get("quantity"),{line.set("quantity",it)},Modifier.weight(1f),number=true)
            Field("Rate (₹)",line.get("rate"),{line.set("rate",it)},Modifier.weight(1f),number=true)
        }
        Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){
            Column(Modifier.weight(1f)){Choice("Line discount",line.discountMode,listOf("percent" to "Percentage (%)","amount" to "Fixed amount (₹)"),{line.chooseDiscountMode(it)});val discountKey=if(line.discountMode=="amount")"discount_amount"else"discount_percent";Field(if(line.discountMode=="amount")"Discount (₹)"else"Discount (%)",line.get(discountKey),{line.set(discountKey,it)},number=true)}
            if(editor.regular||editor.purchase)Field("GST (%)",line.get("gst_rate"),{line.set("gst_rate",it)},Modifier.weight(1f),number=true)
        }
        var expanded by remember{mutableStateOf(false)}
        TextButton(onClick={expanded=!expanded}){Text(if(expanded)"Hide item options"else"HSN, MRP & tax options");Icon(if(expanded)Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore,null)}
        if(expanded){
            Field("HSN / SAC",line.get("hsn"),{line.set("hsn",it)},maximum=16)
            Field("Unit",line.get("unit"),{line.set("unit",it)},maximum=24)
            Field("MRP · reference only (₹)",line.get("mrp"),{line.set("mrp",it)},number=true)
            Toggle("Price includes GST",line.get("price_includes_tax")=="true",{line.set("price_includes_tax",it.toString())})
            if(editor.regular||editor.purchase){
                Choice("Supply classification",line.get("tax_treatment"),supplyChoices,{line.set("tax_treatment",it);if(it!="taxable")line.set("gst_rate","0")})
                if(editor.regular&&editor.purchase)Choice("Supplier GST treatment",line.get("itc_treatment"),listOf("pending_review" to "Input credit pending review","ineligible" to "Ineligible · include GST in cost"),{line.set("itc_treatment",it)})
            }
        }
        TextButton(onClick={editor.lines.remove(line)}){Icon(Icons.Outlined.DeleteOutline,null);Text("Remove item")}
    }
}
@Composable private fun PaymentFields(editor:EntryEditor){Section("Apply this payment"){Toggle("Advance for later allocation",editor.flag("is_advance"),{editor.set("is_advance",it.toString())});if(editor.flag("is_advance")){Text("This stays in the advance account until applied or refunded.");if(editor.kind=="payment_in"&&editor.regular){Choice("Advance relates to",editor.get("advance_supply"),listOf("goods" to "Goods","services" to "Services"),{editor.set("advance_supply",it)});if(editor.get("advance_supply")=="services"){Field("GST rate · included in received amount (%)",editor.get("advance_gst_rate"),{editor.set("advance_gst_rate",it)},number=true);Field("Place of supply · state code",editor.get("place_of_supply"),{editor.set("place_of_supply",it)},maximum=2)}}}else{val targets=editor.targets();editor.allocations.forEachIndexed{index,row->key(row){Choice("Invoice / bill ${index+1}",row.documentId,listOf("" to "Choose document")+targets.filter{target->(index==0||editor.get("name").isBlank()||target.s("name").trim().equals(editor.get("name").trim(),true))&&editor.allocations.none{it!==row&&it.documentId==target.s("id")}}.map{it.s("id") to "${it.s("number")} · ${it.s("name")} · ${money(editor.available(it))} available"},{id->editor.chooseAllocation(row,index,id)});Field("Allocated (₹)",row.amount,{row.amount=it},number=true);TextButton(onClick={editor.allocations.remove(row)}){Text("Remove allocation")}}};OutlinedButton(onClick={editor.allocations.add(AllocationState())}){Text("Add another document")};val total=editor.allocations.fold(java.math.BigDecimal.ZERO){sum,row->sum+(row.amount.toBigDecimalOrNull()?:java.math.BigDecimal.ZERO)};Text("Allocated ${money(total)} of ${money(editor.get("amount"))}")}}}

@Composable fun CompanyDialog(vm:AppModel){val edit=vm.companyEdit;var name by remember{mutableStateOf(if(edit)vm.company.s("name")else"")};var bookLabel by remember{mutableStateOf(if(edit)vm.company.s("book_label")else"")};var mode by remember{mutableStateOf(if(edit)vm.company.s("tax_mode")else"unregistered")};var gstin by remember{mutableStateOf(if(edit)vm.company.s("gstin")else"")};var state by remember{mutableStateOf(if(edit)vm.company.s("state_code")else"")};var address by remember{mutableStateOf(if(edit)vm.company.s("address")else"")};val initial=remember{listOf(name,mode,gstin,state,address,bookLabel)};ActionDialog(if(edit)"Company details"else"Create company",vm,hasChanges={listOf(name,mode,gstin,state,address,bookLabel)!=initial},onDismiss={vm.companyForm=false},onSave={val body=JSONObject().put("name",name.trim()).put("gstin",gstin.trim().uppercase()).put("state_code",state).put("address",address);if(vm.supports("company_book_labels"))body.put("book_label",bookLabel.trim());if(!edit)body.put("tax_mode",mode);val result=vm.api.request(if(edit)vm.api.company(vm.companyId)else"/api/companies",if(edit)"PATCH"else"POST",body)as JSONObject;vm.companyForm=false;vm.loadCompanies(result.s("id"))}){Text("Each company keeps separate books. Choose the tax mode carefully; it cannot be changed here after creation.",style=MaterialTheme.typography.bodySmall);Field("Legal company name",name,{name=it},maximum=120);if(vm.supports("company_book_labels")){Field("Book label · optional",bookLabel,{bookLabel=it},maximum=80);Text("A private workspace label, such as FY 2026–27. Does not change the legal company name on invoices.",style=MaterialTheme.typography.bodySmall)}else FeatureUpgradeHint(vm);Choice("Tax registration",mode,listOf("unregistered" to "Not GST registered","regular" to "GST registered · regular","composition" to "GST registered · composition"),{mode=it},enabled=!edit);Field("GSTIN · required for regular GST",gstin,{gstin=it.uppercase();if(it.length>=2)state=it.take(2)},maximum=15);Field("State code",state,{state=it},maximum=2);Field("Company address",address,{address=it},multiline=true,maximum=500)}}
