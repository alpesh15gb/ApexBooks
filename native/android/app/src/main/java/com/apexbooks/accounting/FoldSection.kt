package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier

@Composable fun FoldSection(title:String,content:@Composable ColumnScope.()->Unit){
    var expanded by remember{mutableStateOf(false)}
    Section{TextButton(onClick={expanded=!expanded},modifier=Modifier.fillMaxWidth()){Text(title,Modifier.weight(1f));Icon(if(expanded)Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore,null)};if(expanded)content()}
}
