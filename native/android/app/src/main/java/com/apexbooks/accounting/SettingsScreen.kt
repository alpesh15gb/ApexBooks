package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.material.icons.outlined.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

private data class SettingGroup(val title:String,val detail:String,val actions:List<Pair<String,()->Unit>>)
@Composable fun SettingsScreen(vm:AppModel){
    var query by remember(vm.companyId){mutableStateOf("")};var category by remember(vm.companyId){mutableStateOf("all")}
    fun tool(key:String){vm.error="";vm.toolData=null;vm.tool=key}
    val groups=buildList {
        add(SettingGroup("Company",vm.company.optString("name")+" · "+friendly(vm.company.optString("tax_mode")),buildList{
            if(vm.isOwner)add("Edit company details" to {vm.companyEdit=true;vm.companyForm=true})
            add("Create another company" to {vm.companyEdit=false;vm.companyForm=true})
        }))
        if(vm.isOwner){
            add(SettingGroup("Documents & branding","Company logo, signature, bank / UPI details and five formats.",listOf("Logo, signature and formats" to {tool("branding")},"Transaction prefixes" to {tool("prefixes")})))
            add(SettingGroup("Accounting","Opening balances and accounting period controls.",listOf("Opening balances" to {tool("openings")},"Accounting period lock" to {tool("period")})))
            add(SettingGroup("Data & migration","Import, export and protect your books. Vyapar includes reconciliation; backup restore creates a separate company.",listOf("Import Vyapar .vyb backup" to {tool("vyapar")},"Import parties / items CSV" to {tool("master_import")},"Export company data" to {tool("data_export")},"Download backup" to {tool("backup")},"Restore company backup" to {tool("restore")})))
            add(SettingGroup("People & access","Manage company roles and permissions.",listOf("Company members" to {tool("members")})))
        }
        add(SettingGroup("Ecommerce","Company-scoped Bagisto channels, stock, orders and delivery review.",listOf("Open ecommerce workspace" to {vm.navigate("commerce")})))
        add(SettingGroup("Account security","Protect your account and review changes. Remembered sign-in is stored securely on this device.",listOf("Password and sessions" to {tool("security")},"One-use recovery codes" to {tool("recovery")},"View audit history" to {tool("audit")})))
    }
    val matches=groups.filter{g->(query.isNotBlank()||category=="all"||g.title==category)&&(g.title+" "+g.detail+" "+g.actions.joinToString(" "){it.first}).contains(query.trim(),true)}
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(16.dp)){
        item{Heading("Make it yours", "Company preferences, documents and account controls.")}
        item{SearchBarField("Search settings",query){query=it}}
        item{Row(Modifier.horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(8.dp)){(listOf("all" to "All")+groups.map{it.title to it.title}).forEach{(key,label)->FilterChip(selected=category==key,onClick={category=key},label={Text(label)})}}}
        items(matches,key={it.title}){group->Column(verticalArrangement=Arrangement.spacedBy(10.dp)){
            Text(group.title.uppercase(),style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant,fontWeight=FontWeight.Bold)
            Surface(shape=RoundedCornerShape(20.dp),color=Color.White){Column{
                group.actions.filter{query.isBlank()||(group.title+" "+group.detail+" "+it.first).contains(query.trim(),true)}.forEachIndexed{index,(label,action)->
                    NativeActionRow(label,icon=when(group.title){"Company"->Icons.Outlined.Business;"Documents & branding"->Icons.Outlined.Palette;"Data & migration"->Icons.Outlined.CloudUpload;"People & access"->Icons.Outlined.People;"Account security"->Icons.Outlined.Shield;"Ecommerce"->Icons.Outlined.ShoppingBag;else->Icons.Outlined.AccountBalance},onClick=action)
                    if(index<group.actions.lastIndex)HorizontalDivider(Modifier.padding(start=74.dp))
                }
            }}
            Text(group.detail,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }}
        if(matches.isEmpty())item{Section{Text("No settings match. Try logo, backup or company.")}}
        item{Text("Apex Books for Android · "+BuildConfig.VERSION_NAME+"\nBuild · "+BuildConfig.BUILD_REVISION+"\nConnected API · "+vm.apiVersion+"\nAPI build · "+vm.apiBuildRevision,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}
    }
}
