@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.apexbooks.accounting

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*

@Composable fun SearchBarField(hint: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(value = value, onValueChange = onChange, modifier = Modifier.fillMaxWidth(), placeholder = { Text(hint, maxLines = 1, overflow = TextOverflow.Ellipsis) }, leadingIcon = { Icon(Icons.Outlined.Search, null) }, trailingIcon = { if (value.isNotBlank()) IconButton(onClick = { onChange("") }) { Icon(Icons.Outlined.Close, "Clear search") } }, singleLine = true, shape = RoundedCornerShape(18.dp), colors = OutlinedTextFieldDefaults.colors(unfocusedBorderColor = Color.Transparent, focusedBorderColor = ApexGreen, unfocusedContainerColor = Color.White, focusedContainerColor = Color.White))
}

@Composable fun NativeActionRow(title: String, subtitle: String = "", icon: ImageVector, onClick: () -> Unit) {
    ListItem(headlineContent = { Text(title, fontWeight = FontWeight.Medium) }, supportingContent = if (subtitle.isBlank()) null else ({ Text(subtitle) }), leadingContent = {
        Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(14.dp)) { Icon(icon, null, Modifier.padding(12.dp).size(22.dp), tint = ApexGreen) }
    }, trailingContent = { Icon(Icons.Outlined.ChevronRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant) }, modifier = Modifier.clickable(onClick = onClick).padding(vertical = 3.dp), colors = ListItemDefaults.colors(containerColor = Color.Transparent))
}

@Composable fun MoreScreen(vm: AppModel) {
    var query by remember { mutableStateOf("") }
    var confirmSignOut by remember { mutableStateOf(false) }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        item { SearchBarField("Find a workspace", query) { query = it } }
        item { Section {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(16.dp)) { Icon(Icons.Outlined.Business, null, Modifier.padding(16.dp), tint = ApexGreen) }
                Column(Modifier.weight(1f)) { Text(companyDisplayName(vm.company), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold); Text(friendly(vm.company.s("tax_mode")) + " · " + friendly(vm.company.s("role")), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
        } }
        vm.navigation.filter { it.key !in setOf("dashboard", "party", "reports") && (it.title + " " + it.group).contains(query.trim(), true) }.groupBy { it.group }.forEach { (group, features) ->
            item { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(group.uppercase(), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Surface(shape = RoundedCornerShape(20.dp), color = Color.White) { Column { features.forEachIndexed { index, feature -> NativeActionRow(feature.title, icon = featureIcon(feature.key), onClick = { vm.navigate(feature.key) }); if (index < features.lastIndex) HorizontalDivider(Modifier.padding(start = 74.dp)) } } }
            } }
        }
        item { OutlinedButton(onClick = { if(vm.heldSaleCount>0)confirmSignOut=true else vm.task { vm.logout() } }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.AutoMirrored.Outlined.Logout, null); Spacer(Modifier.width(8.dp)); Text("Sign out") } }
        item { Text("Apex Books ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
    if(confirmSignOut)AlertDialog(onDismissRequest={confirmSignOut=false},title={Text("Discard held carts and sign out?")},text={Text("${vm.heldSaleCount} company cart(s) are held only in this session. Signing out discards them. Resolve any sale with an unknown save outcome before leaving.")},confirmButton={TextButton(onClick={confirmSignOut=false;vm.task{vm.logout()}}){Text("Sign out and discard")}},dismissButton={TextButton(onClick={confirmSignOut=false}){Text("Keep working")}})
}

@Composable fun CreateTransactionSheet(vm: AppModel, close: () -> Unit) {
    var category by remember { mutableStateOf(when (vm.page) { in MobileNavigation.purchases -> "Purchases"; "party", "item" -> "Contacts & items"; else -> "Sales" }) }
    ModalBottomSheet(onDismissRequest = close) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp)) {
            Heading("Create an entry", vm.company.s("name"))
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) { listOf("Sales", "Purchases", "Contacts & items").forEach { label -> FilterChip(selected = category == label, onClick = { category = label }, label = { Text(label) }) } }
            val kinds = when (category) { "Purchases" -> MobileNavigation.purchases; "Contacts & items" -> listOf("party", "item"); else -> MobileNavigation.sales }
            LazyColumn(Modifier.heightIn(max = 450.dp)) { items(kinds, key = { it }) { kind -> NativeActionRow(vm.title(kind), when (kind) { "sales_invoice" -> "Bill a customer"; "purchase_bill" -> "Enter or scan a supplier bill"; "payment_in" -> "Record money received from a customer"; "payment_out" -> "Record a payment to a supplier"; "estimate" -> "Send a quote before invoicing"; "proforma" -> "Prepare a preliminary invoice"; "sales_order" -> "Confirm a customer order"; "purchase_order" -> "Place an order with a supplier"; "credit_note" -> "Reduce an invoice or record a sales return"; "debit_note" -> "Reduce a bill or record a purchase return"; "expense" -> "Record a business cost paid now"; "party" -> "Save a customer or supplier"; "item" -> "Save a product or service"; "pos" -> "Open the point of sale"; else -> "" }, featureIcon(kind)) { close(); if (kind == "pos") vm.navigate(kind) else vm.add(kind) } } }
            Spacer(Modifier.height(24.dp))
        }
    }
}
