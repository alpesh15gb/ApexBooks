@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.apexbooks.accounting

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import com.apexbooks.accounting.data.*
import org.json.JSONObject

@Composable fun ApexWorkspace(vm: AppModel, activity: MainActivity) {
    if (!vm.signedIn) { LoginScreen(vm); return }
    var companies by remember { mutableStateOf(false) }
    var companyQuery by remember { mutableStateOf("") }
    var searchOpen by remember { mutableStateOf(false) }
    var createOpen by remember { mutableStateOf(false) }
    var lastEntry by rememberSaveable { mutableStateOf("sales_invoice") }
    val currentTab = MobileNavigation.tab(vm.page)
    val canCreate = vm.canWrite && vm.recordsReady && vm.companyId.isNotBlank()
    val pageCreates = currentTab == "transactions" || vm.page in setOf("party", "item")
    fun navigate(key: String) {
        vm.navigate(if (key == "transactions") MobileNavigation.entryDestination(lastEntry) else key)
    }
    LaunchedEffect(vm.page) { if (MobileNavigation.tab(vm.page) == "transactions") lastEntry = vm.page }
    BackHandler(enabled = vm.page != "dashboard" && vm.editor == null && vm.detail == null && vm.pdf == null && vm.statement == null && vm.tool.isBlank() && !vm.companyForm && !searchOpen && !createOpen && !companies) { vm.navigate("dashboard") }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val wide = MobileNavigation.usesRail(maxWidth.value, maxHeight.value)
        Row(Modifier.fillMaxSize()) {
            if (wide) NavigationRail(containerColor = MaterialTheme.colorScheme.surface) {
                MobileNavigation.primary.forEach { (key, label) ->
                    NavigationRailItem(modifier = Modifier.semantics { contentDescription = label },
                        selected = key == currentTab, onClick = { navigate(key) },
                        icon = { Icon(mobileIcon(key), null) }, label = { Text(label, Modifier.clearAndSetSemantics {}) },
                        colors = NavigationRailItemDefaults.colors(indicatorColor = MaterialTheme.colorScheme.primaryContainer))
                }
            }
            Scaffold(
                modifier = Modifier.weight(1f).imePadding(),
                containerColor = MaterialTheme.colorScheme.background,
                topBar = { Column {
                    TopAppBar(title = {
                        Text(when (vm.page) {
                            "dashboard" -> "Business overview"
                            "pos" -> "Point of sale"
                            "more" -> "Workspace"
                            else -> vm.title(vm.page)
                        }, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }, actions = {
                        if (canCreate && !pageCreates && vm.page != "pos") {
                            IconButton(onClick = { createOpen = true }) { Icon(Icons.Outlined.Add, "Create entry") }
                        }
                        IconButton(onClick = { searchOpen = true }, enabled = vm.companyId.isNotBlank()) { Icon(Icons.Outlined.Search, "Search workspace") }
                        IconButton(onClick = { vm.task { vm.refresh() } }, enabled = vm.busy == 0 && vm.companyId.isNotBlank()) { Icon(Icons.Outlined.Refresh, "Refresh") }
                    }, colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White))
                    key(vm.companyId, companyDisplayName(vm.company)) { Row(Modifier.fillMaxWidth().semantics{contentDescription="Switch company"}
                        .clickable(role=Role.Button,onClickLabel="Switch company"){companyQuery="";companies=true}
                        .heightIn(min=48.dp).background(Color.White).padding(horizontal=16.dp,vertical=10.dp),
                        verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)){
                        Icon(Icons.Outlined.Business,null,Modifier.size(18.dp),tint=ApexGreen)
                        Text(companyDisplayName(vm.company).ifBlank{"Choose company"},Modifier.weight(1f),style=MaterialTheme.typography.bodyMedium,maxLines=1,overflow=TextOverflow.Ellipsis,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Icon(Icons.Outlined.ExpandMore,null,Modifier.size(20.dp))
                    }
                    }
                    if (vm.busy > 0) LinearProgressIndicator(Modifier.fillMaxWidth()) else HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
                } },
                bottomBar = { if (!wide && !WindowInsets.isImeVisible) {
                    Surface(shadowElevation = 10.dp, color = Color.White) { NavigationBar(containerColor = Color.White, tonalElevation = 0.dp) {
                        MobileNavigation.primary.forEach { (key, label) ->
                            NavigationBarItem(modifier = Modifier.semantics { contentDescription = label },
                                selected = currentTab == key, onClick = { navigate(key) },
                                icon = { Icon(mobileIcon(key), null) },
                                label = { Text(label, Modifier.clearAndSetSemantics {}, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                                colors = NavigationBarItemDefaults.colors(indicatorColor = MaterialTheme.colorScheme.primaryContainer))
                        }
                    } }
                } },
                floatingActionButton = { if (canCreate && pageCreates && !WindowInsets.isImeVisible) {
                    ExtendedFloatingActionButton(onClick = { vm.add(vm.page) }, icon = { Icon(Icons.Outlined.Add, null) }, text = { Text(MobileNavigation.createLabel(vm.page)) }, containerColor = ApexGreen, contentColor = Color.White)
                } }
            ) { padding -> Column(Modifier.padding(padding).fillMaxSize()) {
                if(BuildConfig.DEBUG)Text("Test workspace · ${java.net.URI(BuildConfig.API_ORIGIN).host}",Modifier.padding(horizontal=16.dp),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                if(vm.capabilityRetryable)Row(Modifier.padding(horizontal=16.dp),verticalAlignment=Alignment.CenterVertically){Text(vm.capabilityHint,Modifier.weight(1f),style=MaterialTheme.typography.bodySmall);TextButton(enabled=!vm.capabilityChecking,onClick={vm.retryCapabilities()}){Text("Retry features")}}
                if (vm.error.isNotBlank()) Box(Modifier.padding(16.dp, 6.dp)) { Message(vm.error, true) { vm.error = "" } }
                if (vm.notice.isNotBlank()) Box(Modifier.padding(16.dp, 6.dp)) { Message(vm.notice) { vm.notice = "" } }
                if (vm.companyId.isBlank()) Column(Modifier.padding(24.dp)) {
                    Heading("Create your first company", "Keep each business in its own books. Choose GST or non-GST accounting, then add an invoice, purchase or opening balance.")
                    Button(onClick = { vm.companyEdit = false; vm.companyForm = true }) { Text("Create company") }
                } else AnimatedContent(targetState = vm.page, modifier = Modifier.fillMaxSize(), label = "Workspace destination") { page -> key(vm.companyId, page) {
                    if(!vm.recordsReady && page !in setOf("more","settings"))Column(Modifier.padding(24.dp)){Heading("Loading company history","Waiting for complete records before showing balances or starting billing.");if(vm.busy==0)Button(onClick={vm.task{vm.refresh()}}){Text("Retry company data")}}else when (page) {
                        "dashboard" -> DashboardScreen(vm)
                        "reports" -> ReportsScreen(vm)
                        "more" -> MoreScreen(vm)
                        "bank" -> BankScreen(vm)
                        "ledger" -> LedgerScreen(vm)
                        "day_book" -> DayBookScreen(vm)
                        "settings" -> SettingsScreen(vm)
                        "commerce" -> CommerceScreen(vm)
                        "pos" -> PosScreen(vm)
                        else -> RegisterScreen(vm)
                    }
                } }
            } }
        }
    }
    if (companies) ModalBottomSheet(onDismissRequest = { companies = false }) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp)) {
            Heading("Switch company", "Each company keeps its own books and settings.")
            Spacer(Modifier.height(12.dp))
            SearchBarField("Search your companies", companyQuery) { companyQuery = it }
            if(vm.companies.none{companySearchText(it).contains(companyQuery.trim(),true)})Text("No companies match this search. Clear the search or create a separate company.",Modifier.padding(vertical=16.dp),style=MaterialTheme.typography.bodyMedium)
            LazyColumn(Modifier.weight(1f, false).padding(vertical = 12.dp)) { items(vm.companies.filter { companySearchText(it).contains(companyQuery.trim(), true) }, key = { it.s("id") }) { row ->
                ListItem(headlineContent = { Text(companyDisplayName(row), fontWeight = FontWeight.SemiBold) }, supportingContent = { Text((if (row.s("tax_mode") == "regular") row.s("gstin") else friendly(row.s("tax_mode")))+" · "+friendly(row.s("role"))) }, leadingContent = { Icon(Icons.Outlined.Business, null) }, trailingContent = { if (row.s("id") == vm.companyId) Icon(Icons.Outlined.CheckCircle, "Selected", tint = ApexGreen) }, modifier = Modifier.clickable { companies = false; vm.task { vm.chooseCompany(row) } })
            } }
            OutlinedButton(onClick = { companies = false; vm.companyEdit = false; vm.companyForm = true }, modifier = Modifier.fillMaxWidth()) { Text("Create another company") }
            Spacer(Modifier.height(24.dp))
        }
    }
    if (createOpen) CreateTransactionSheet(vm) { createOpen = false }
    if (searchOpen) WorkspaceSearch(vm) { searchOpen = false }
    vm.detail?.takeIf{vm.recordsReady}?.let { TransactionDetail(vm, it) }
    vm.editor?.let { key(it) { EntryScreen(it) } }
    if (vm.companyForm) CompanyDialog(vm)
    vm.statement?.takeIf{vm.recordsReady}?.let { PartyStatementScreen(vm, it) }
    if (vm.tool.isNotBlank()) ToolsScreen(vm)
    vm.pdf?.takeIf{vm.recordsReady}?.let { PdfScreen(vm, activity, it) }
}

private fun mobileIcon(key: String) = when (key) {
    "transactions" -> Icons.Outlined.SwapHoriz
    "more" -> Icons.Outlined.GridView
    else -> featureIcon(key)
}

internal fun searchWorkspaceRecords(records: List<JSONObject>, query: String): List<JSONObject> {
    val term = query.trim()
    if (term.isBlank()) return emptyList()
    val ranked = List(3) { mutableListOf<JSONObject>() }
    for (record in records) {
        val kind = record.s("kind")
        val name = record.s("name")
        val number = record.s("number")
        val data = record.optJSONObject("data")
        val barcode = if (kind == "item") data?.s("barcode").orEmpty() else ""
        val secondary = when (kind) {
            "item" -> data?.s("hsn").orEmpty()
            "party" -> data?.s("phone").orEmpty()
            else -> ""
        }
        val rank = when {
            name.equals(term, true) || number.equals(term, true) || barcode.equals(term, true) -> 0
            name.startsWith(term, true) || number.startsWith(term, true) || barcode.startsWith(term, true) -> 1
            name.contains(term, true) || number.contains(term, true) || barcode.contains(term, true)
                || secondary.contains(term, true) -> 2
            else -> continue
        }
        if (ranked[rank].size < 30) ranked[rank].add(record)
        if (ranked[0].size == 30) break
    }
    return ranked.flatten().take(30)
}

@Composable private fun WorkspaceSearch(vm: AppModel, close: () -> Unit) {
    var query by remember { mutableStateOf("") }
    val search = query.trim()
    val workspaces = remember(search, vm.navigation) {
        if (search.isBlank()) emptyList() else vm.navigation.filter { it.title.contains(search, true) }
    }
    val matches = remember(search, vm.records) { searchWorkspaceRecords(vm.records, search) }
    ModalBottomSheet(onDismissRequest = close) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp)) {
            Heading("Search this company")
            Spacer(Modifier.height(12.dp))
            SearchBarField("Name, reference or barcode", query) { query = it }
            LazyColumn(Modifier.fillMaxWidth().heightIn(max = 460.dp)) {
                if (workspaces.isNotEmpty()) item {
                    Text("Workspaces", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.labelMedium)
                }
                items(workspaces, key = { "section-" + it.key }) { hit ->
                    ListItem(headlineContent = { Text(hit.title) }, leadingContent = { Icon(featureIcon(hit.key), null) },
                        modifier = Modifier.clickable(role = Role.Button) { close(); vm.navigate(hit.key) })
                }
                if (matches.isNotEmpty()) item {
                    Text("Records", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.labelMedium)
                }
                items(matches, key = { it.s("id") }) { row ->
                    val kind = row.s("kind")
                    val number = row.s("number")
                    ListItem(
                        headlineContent = { Text(number.ifBlank { row.s("name") }) },
                        supportingContent = { Text(if (number.isBlank()) friendly(kind) else "${row.s("name")} · ${friendly(kind)}") },
                        leadingContent = { Icon(featureIcon(kind), null) },
                        modifier = Modifier.clickable(role = Role.Button) {
                            close()
                            if (kind == "party") vm.statement = row else vm.detail = row
                        },
                    )
                }
                if (search.isNotBlank() && workspaces.isEmpty() && matches.isEmpty()) item {
                    Text("No matches. Try a name, document number or barcode.", Modifier.padding(vertical = 16.dp))
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}
