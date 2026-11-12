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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.LocalDensity
import com.apexbooks.accounting.data.*

@Composable fun ApexWorkspace(vm: AppModel, activity: MainActivity) {
    if (!vm.signedIn) { LoginScreen(vm); return }
    var companies by remember { mutableStateOf(false) }
    var companyQuery by remember { mutableStateOf("") }
    var searchOpen by remember { mutableStateOf(false) }
    var createOpen by remember { mutableStateOf(false) }
    val currentTab = MobileNavigation.tab(vm.page)
    val destinations = listOf("dashboard" to "Home", "transactions" to "Transactions", "party" to "Parties", "reports" to "Reports", "more" to "More")
    fun navigate(key: String) = vm.navigate(if (key == "transactions") "sales_invoice" else key)
    BackHandler(enabled = vm.page != "dashboard" && vm.editor == null && vm.detail == null && vm.pdf == null && vm.statement == null && vm.tool.isBlank() && !vm.companyForm && !searchOpen && !createOpen && !companies) { vm.navigate("dashboard") }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val wide = maxWidth >= 840.dp
        val compactLabels = maxWidth / LocalDensity.current.fontScale < 600.dp
        Row(Modifier.fillMaxSize()) {
            if (wide) NavigationRail(containerColor = Color.White, header = { AppLogo(Modifier.width(100.dp).padding(8.dp)) }) {
                destinations.forEach { (key, label) -> NavigationRailItem(selected = key == currentTab, onClick = { navigate(key) }, icon = { Icon(mobileIcon(key), null) }, label = { Text(label) }) }
            }
            Scaffold(
                modifier = Modifier.weight(1f).imePadding(),
                containerColor = MaterialTheme.colorScheme.background,
                topBar = { Column {
                    TopAppBar(title = {
                        Text(when { vm.page == "dashboard" -> "Business overview"; currentTab == "transactions" -> vm.title(vm.page); vm.page == "more" -> "Workspace"; else -> vm.title(vm.page) }, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }, actions = {
                        if(vm.canWrite && vm.recordsReady && vm.companyId.isNotBlank()) IconButton(onClick = { createOpen = true }) { Icon(Icons.Outlined.Add, "Create entry") }
                        IconButton(onClick = { searchOpen = true }, enabled = vm.companyId.isNotBlank()) { Icon(Icons.Outlined.Search, "Search workspace") }
                        IconButton(onClick = { vm.task { vm.refresh() } }, enabled = vm.busy == 0 && vm.companyId.isNotBlank()) { Icon(Icons.Outlined.Refresh, "Refresh") }
                    }, colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White))
                    key(vm.companyId, companyDisplayName(vm.company)) { Row(Modifier.fillMaxWidth().semantics{contentDescription="Switch company"}
                        .clickable(role=Role.Button,onClickLabel="Switch company"){companyQuery="";companies=true}
                        .heightIn(min=48.dp).background(Color.White).padding(horizontal=20.dp,vertical=10.dp),
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
                        destinations.forEach { (key, label) -> NavigationBarItem(modifier=Modifier.semantics{contentDescription=label}, selected = currentTab == key, onClick = { navigate(key) }, icon = { Icon(mobileIcon(key), null) }, label = { Text(if(compactLabels&&key=="transactions")"Entries"else label, maxLines = 1, overflow=TextOverflow.Ellipsis) }, colors = NavigationBarItemDefaults.colors(indicatorColor = MaterialTheme.colorScheme.primaryContainer)) }
                    } }
                } },
                floatingActionButton = { if (vm.canWrite && vm.recordsReady && vm.companyId.isNotBlank() && vm.page !in setOf("dashboard", "reports", "settings", "more", "commerce", "pos") && !WindowInsets.isImeVisible) {
                    ExtendedFloatingActionButton(onClick = { if (vm.page in MobileNavigation.transactions || vm.page in setOf("party", "item")) vm.add(vm.page) else createOpen = true }, icon = { Icon(Icons.Outlined.Add, null) }, text = { Text(MobileNavigation.createLabel(vm.page)) }, containerColor = ApexGreen, contentColor = Color.White)
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
                    if(!vm.recordsReady && page !in setOf("dashboard","reports","more","settings"))Column(Modifier.padding(24.dp)){Heading("Loading company history","Waiting for complete records before showing balances or starting billing.");if(vm.busy==0)Button(onClick={vm.task{vm.refresh()}}){Text("Retry company data")}}else when (page) {
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
    vm.detail?.let { TransactionDetail(vm, it) }
    vm.editor?.let { key(it) { EntryScreen(it) } }
    if (vm.companyForm) CompanyDialog(vm)
    vm.statement?.let { PartyStatementScreen(vm, it) }
    if (vm.tool.isNotBlank()) ToolsScreen(vm)
    vm.pdf?.let { PdfScreen(vm, activity, it) }
}

private fun mobileIcon(key: String) = when (key) {
    "transactions" -> Icons.Outlined.SwapHoriz
    "more" -> Icons.Outlined.GridView
    else -> featureIcon(key)
}

@Composable private fun WorkspaceSearch(vm: AppModel, close: () -> Unit) {
    var query by remember { mutableStateOf("") }
    ModalBottomSheet(onDismissRequest = close) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp)) {
            Heading("Find anything")
            Spacer(Modifier.height(12.dp))
            SearchBarField("Parties, invoices, items or sections", query) { query = it }
            LazyColumn(Modifier.fillMaxWidth().heightIn(max = 460.dp)) {
                if (query.isNotBlank()) {
                    items(vm.navigation.filter { it.title.contains(query.trim(), true) }, key = { "section-" + it.key }) { hit ->
                        ListItem(headlineContent = { Text(hit.title) }, supportingContent = { Text("Open section") }, leadingContent = { Icon(featureIcon(hit.key), null) }, modifier = Modifier.clickable { close(); vm.navigate(hit.key) })
                    }
                    val rows = vm.records.filter { (it.s("name") + " " + it.s("number")).contains(query.trim(), true) }.take(30)
                    items(rows, key = { it.s("id") }) { row -> ListItem(headlineContent = { Text(row.s("number").ifBlank { row.s("name") }) }, supportingContent = { Text(row.s("name") + " · " + friendly(row.s("kind"))) }, leadingContent = { Icon(featureIcon(row.s("kind")), null) }, modifier = Modifier.clickable { close(); if (row.s("kind") == "party") vm.statement = row else if (row.s("kind") == "item") { vm.navigate("item"); if (vm.canWrite) vm.edit(row) } else vm.detail = row }) }
                    if (rows.isEmpty() && vm.navigation.none { it.title.contains(query.trim(), true) }) item { Text("No matches. Try a party name or document number.", Modifier.padding(16.dp)) }
                } else item { Text("Search across the current company.", Modifier.padding(vertical = 24.dp), color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}
