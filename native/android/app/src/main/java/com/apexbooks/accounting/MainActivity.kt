@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
package com.apexbooks.accounting

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.automirrored.outlined.MenuBook
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.launch
import org.json.JSONObject

class MainActivity:ComponentActivity(){private val vm by viewModels<AppModel>();override fun onCreate(savedInstanceState:Bundle?){super.onCreate(savedInstanceState);enableEdgeToEdge();setContent{ApexTheme{val open=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()){vm.files.picked(it)};val save=rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")){vm.task{vm.files.saved(it)}};val camera=rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()){vm.files.captured(it)};SideEffect{vm.files.launchOpen={open.launch(it)};vm.files.launchSave={save.launch(it)};vm.files.launchCamera={camera.launch(it)}};ApexApp(vm,this)}}}}

fun featureIcon(key:String):ImageVector=when(key){"dashboard"->Icons.Outlined.Dashboard;"party"->Icons.Outlined.People;"item"->Icons.Outlined.Inventory2;"bank"->Icons.Outlined.AccountBalance;"ledger"->Icons.AutoMirrored.Outlined.MenuBook;"reports"->Icons.Outlined.Assessment;"settings"->Icons.Outlined.Settings;"pos"->Icons.Outlined.PointOfSale;"purchase_bill","purchase_order","payment_out","expense","debit_note"->Icons.Outlined.ShoppingBag;else->Icons.AutoMirrored.Outlined.ReceiptLong}

@Composable fun ApexApp(vm:AppModel,activity:MainActivity){ApexWorkspace(vm,activity)}

