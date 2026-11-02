package com.apexbooks.accounting

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.delay
import org.json.JSONObject
import java.math.BigDecimal

@Composable fun PosScreen(vm:AppModel){val cid=vm.companyId;val editor=remember(cid){vm.saleDraft()};var search by remember(cid){mutableStateOf("")};var historySearch by remember(cid){mutableStateOf("")};var tab by remember(cid){mutableIntStateOf(0)};var advanced by remember{mutableStateOf(false)};var saving by remember(cid){mutableStateOf(false)};var retryPending by remember(cid){mutableStateOf(editor.submission.unresolved)};val stamp=remember(cid){vm.workspaceStamp()};var receipt by remember(cid){mutableStateOf<JSONObject?>(null)};val products=vm.records.filter{it.s("kind")=="item"};var preview by remember{mutableStateOf<JSONObject?>(null)};var previewError by remember{mutableStateOf("")}
    fun add(item:JSONObject){if(saving||!vm.canWrite)return;val existing=editor.lines.find{it.get("item_id")==item.s("id")};if(existing!=null)existing.set("quantity",((existing.get("quantity").toBigDecimalOrNull()?:BigDecimal.ZERO)+BigDecimal.ONE).toPlainString())else{val line=LineState(regular=vm.regular);editor.chooseItem(line,item.s("id"));editor.lines.add(line)}}
    val serialized=editor.body().toString()
    LaunchedEffect(serialized){preview=null;previewError="";if(editor.lines.isEmpty())return@LaunchedEffect;delay(300);try{preview=vm.api.request(vm.api.company(cid,"/documents/preview"),"POST",JSONObject(serialized))as JSONObject}catch(e:Exception){currentCoroutineContext().ensureActive();if(e is kotlinx.coroutines.CancellationException)throw e;previewError=e.message?:"Total is unavailable.";if(e is ApiFailure&&e.status==401)vm.failure(e)}}
    val catalog:@Composable (Modifier)->Unit={modifier->Column(modifier){OutlinedTextField(search,{search=it},label={Text("Search products / scan barcode")},modifier=Modifier.fillMaxWidth().padding(bottom=12.dp),singleLine=true,keyboardOptions=KeyboardOptions(imeAction=ImeAction.Search),keyboardActions=KeyboardActions(onSearch={val item=products.find{it.o("data").s("barcode").isNotBlank()&&it.o("data").s("barcode")==search.trim()};if(item!=null){add(item);search=""}}));LazyVerticalGrid(GridCells.Adaptive(145.dp),Modifier.weight(1f),horizontalArrangement=Arrangement.spacedBy(10.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){items(products.filter{(it.s("name")+" "+it.o("data").s("barcode")).contains(search,true)},key={it.s("id")}){item->Card(onClick={add(item)},enabled=vm.canWrite&&!saving,colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surface)){Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){DataImage(item.o("data").s("image_thumbnail"),Modifier.fillMaxWidth().height(80.dp));Text(item.s("name"),maxLines=2,style=MaterialTheme.typography.bodyMedium,fontWeight=FontWeight.SemiBold);Text(money(item.o("data").s("sale_rate")),color=ApexGreen,fontWeight=FontWeight.SemiBold)}}}}}}
    val cart:@Composable (Modifier)->Unit={modifier->LazyColumn(modifier,verticalArrangement=Arrangement.spacedBy(12.dp)){item{Section("Customer"){Choice("Saved customer",editor.get("party_id"),listOf("" to "Walk-in / entered customer")+vm.records.filter{it.s("kind")=="party"}.map{it.s("id") to it.s("name")},{if(!saving)editor.chooseParty(it)},enabled=!saving);Field("Customer name",editor.get("name"),{if(!saving)editor.changePartyName(it)},readOnly=saving,maximum=120);TextButton(onClick={advanced=!advanced}){Text(if(advanced)"Hide billing details"else"Billing details")};if(advanced){Field("Address",editor.get("party_address"),{if(!saving)editor.set("party_address",it)},readOnly=saving,multiline=true,maximum=1000);Field("Phone",editor.get("party_phone"),{if(!saving)editor.set("party_phone",it)},readOnly=saving,maximum=32);if(vm.regular){Field("GSTIN",editor.get("party_gstin"),{if(!saving){editor.set("party_gstin",it.uppercase());if(it.length>=2)editor.set("place_of_supply",it.take(2))}},readOnly=saving,maximum=15);Field("Place of supply · state code",editor.get("place_of_supply"),{if(!saving)editor.set("place_of_supply",it)},readOnly=saving,maximum=2)}}}};editor.lines.forEach{line->item(key=line.uiKey){Section(line.get("description")){Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(6.dp)){IconButton(enabled=!saving,onClick={val qty=line.get("quantity").toBigDecimalOrNull()?:BigDecimal.ONE;if(qty>BigDecimal.ONE)line.set("quantity",(qty-BigDecimal.ONE).toPlainString())else editor.lines.remove(line)}){Icon(Icons.Outlined.Remove,"Decrease quantity")};Field("Qty",line.get("quantity"),{if(!saving)line.set("quantity",it)},Modifier.weight(1f),number=true,readOnly=saving);IconButton(enabled=!saving,onClick={line.set("quantity",((line.get("quantity").toBigDecimalOrNull()?:BigDecimal.ZERO)+BigDecimal.ONE).toPlainString())}){Icon(Icons.Outlined.Add,"Increase quantity")};IconButton(enabled=!saving,onClick={editor.lines.remove(line)}){Icon(Icons.Outlined.DeleteOutline,"Remove item")}};Field("Rate (₹)",line.get("rate"),{if(!saving)line.set("rate",it)},number=true,readOnly=saving);Field("Discount (%)",line.get("discount_percent"),{if(!saving)line.set("discount_percent",it)},number=true,readOnly=saving);if(vm.regular)Toggle("Price includes GST",line.get("price_includes_tax")=="true",{line.set("price_includes_tax",it.toString())},enabled=!saving);if(vm.regular){Choice("Supply classification",line.get("tax_treatment"),supplyChoices,{line.set("tax_treatment",it);if(it!="taxable")line.set("gst_rate","0")},enabled=!saving);Field("GST rate (%)",line.get("gst_rate"),{if(!saving)line.set("gst_rate",it)},number=true,readOnly=saving)}}}};if(editor.lines.isEmpty())item{Section{Text("Your cart is empty. Add a product from the catalog.")}};item{Section("Payment"){Choice("Paid through",editor.get("payment_account"),listOf("cash" to "Cash","bank" to "Bank / UPI / card"),{editor.set("payment_account",it)},enabled=!saving);if(editor.get("payment_account")=="bank")Choice("Bank",editor.get("bank_account_id"),vm.banks.map{it.s("id") to it.s("name")},{editor.set("bank_account_id",it)},enabled=!saving)else Field("Cash tendered (₹)",editor.get("tender_amount"),{if(!saving)editor.set("tender_amount",it)},number=true,readOnly=saving);Toggle("Round total to nearest rupee",editor.flag("round_total"),{editor.set("round_total",it.toString())},enabled=!saving)}}}}

    val history: @Composable (Modifier)->Unit={modifier->
        val sales=vm.records.filter{it.s("kind")=="pos"&&(it.s("name")+" "+it.s("number")+" "+it.s("date")).contains(historySearch,true)}
            .sortedWith(compareByDescending<JSONObject>{it.s("date")}.thenByDescending{it.s("number")})
        LazyColumn(modifier,verticalArrangement=Arrangement.spacedBy(12.dp)){
            item{OutlinedTextField(historySearch,{historySearch=it},label={Text("Search sales history")},modifier=Modifier.fillMaxWidth(),singleLine=true)}
            if(sales.isEmpty())item{Section{Text("No sales match this search.")}}
            items(sales,key={it.s("id")}){RecordCard(vm,it)}
        }
    }
    BoxWithConstraints(Modifier.fillMaxSize().padding(16.dp)){
        val wide=maxWidth>=760.dp
        Column{
            if(wide)PrimaryTabRow(if(tab==2)1 else 0){
                Tab(tab!=2,onClick={tab=0},text={Text("New sale")})
                Tab(tab==2,onClick={tab=2},text={Text("Sales history")})
            }else PrimaryTabRow(tab){
                Tab(tab==0,onClick={tab=0},text={Text("Catalog")})
                Tab(tab==1,onClick={tab=1},text={Text("Cart · ${editor.lines.size}")})
                Tab(tab==2,onClick={tab=2},text={Text("Sales history")})
            }
            if(tab==2)history(Modifier.weight(1f))else{
                if(wide)Row(Modifier.weight(1f),horizontalArrangement=Arrangement.spacedBy(16.dp)){
                    catalog(Modifier.weight(1.2f).fillMaxHeight())
                    cart(Modifier.weight(1f).fillMaxHeight())
                }else if(tab==0)catalog(Modifier.weight(1f))else cart(Modifier.weight(1f))
                Surface(tonalElevation=2.dp,shadowElevation=3.dp){
                    Column(Modifier.fillMaxWidth().padding(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
                        Text("Cart held for this company while you navigate. It posts only when you complete the sale; signing out discards it.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        if(previewError.isNotBlank())Text(previewError,color=MaterialTheme.colorScheme.error,style=MaterialTheme.typography.bodySmall)
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                            Text("Total",style=MaterialTheme.typography.titleMedium)
                            Text(preview?.let{money(it.s("amount"))}?:"—",style=MaterialTheme.typography.titleLarge,color=ApexGreen)
                        }
                        val tender=editor.get("tender_amount").toBigDecimalOrNull()
                        if(editor.get("payment_account")=="cash"&&tender!=null&&preview!=null){
                            val difference=tender-preview!!.decimal("amount")
                            Text((if(difference.signum()<0)"Still due "else"Change ")+money(difference.abs()),style=MaterialTheme.typography.bodySmall)
                        }
                        if(retryPending)Text("Retry submits the original sale, not subsequent cart edits. Resolve this sale before starting another.",color=MaterialTheme.colorScheme.error)
                        Button(enabled=vm.canWrite&&!saving&&(retryPending||preview!=null),onClick={
                            if(!wide&&tab==0){tab=1;return@Button}
                            saving=true
                            vm.task{
                                try{
                                    editor.set("date",today())
                                    val candidate=editor.body()
                                    if(editor.get("tender_amount").isBlank())candidate.o("data").put("tender_amount",preview?.s("amount")?:"")
                                    val body=editor.submission.body(candidate)
                                    val result=try{vm.api.saveRecord(cid,body,editor.retryKey)}catch(e:Exception){editor.submission.failed(e);retryPending=editor.submission.unresolved;throw e}
                                    editor.submission.succeeded();retryPending=false
                                    receipt=result
                                    editor.lines.clear()
                                    editor.set("tender_amount","")
                                    editor.renewRetryKey()
                                    if(!vm.inWorkspace(cid,stamp))return@task
                                    preview=null
                                    vm.notice="Sale ${result.s("number")} posted."
                                    vm.refresh()
                                }finally{saving=false}
                            }
                        },modifier=Modifier.fillMaxWidth()){
                            Text(if(saving)"Posting…"else if(!wide&&tab==0)"Review cart"else if(retryPending)"Retry original sale"else"Complete sale")
                        }
                        receipt?.let{row->
                            TextButton(onClick={vm.documentPdf(row)},modifier=Modifier.fillMaxWidth()){
                                Icon(Icons.Outlined.PictureAsPdf,null)
                                Text("View / print ${row.s("number")}")
                            }
                        }
                    }
                }
            }
        }
    }
}
