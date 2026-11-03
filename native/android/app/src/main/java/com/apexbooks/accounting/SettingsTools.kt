package com.apexbooks.accounting

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.*
import org.json.JSONArray
import org.json.JSONObject

@Composable fun BrandingTool(vm:AppModel){val cid=vm.companyId;val values=remember{mutableStateMapOf<String,String>()};var format by remember{mutableStateOf("modern")};var loaded by remember{mutableStateOf(false)}
    LaunchedEffect(Unit){try{val data=vm.api.request(vm.api.company(cid,"/document-branding"))as JSONObject;for(key in listOf("logo","signature","phone","email","bank_name","account_number","ifsc","branch","upi_id","notes","terms"))values[key]=data.s(key);format=(vm.api.request(vm.api.company(cid,"/preferences"))as JSONObject).s("document_template");loaded=true}catch(e:Exception){vm.failure(e)}}
    ActionDialog("Branding and document formats",vm,enabled=loaded,onDismiss={vm.tool=""},onSave={val body=JSONObject();values.filterKeys{it!="logo"}.forEach{(key,value)->body.put(key,value)};vm.api.request(vm.api.company(cid,"/document-branding"),"PUT",body);vm.api.request(vm.api.company(cid,"/preferences"),"PUT",JSONObject().put("document_template",format));vm.tool="";vm.notice="Document branding saved."}){
        if(!loaded)CircularProgressIndicator()else{
            Choice("Default document format",format,listOf("modern" to "Modern","vintage" to "Vintage","mrp_discount" to "MRP + discount","elegant" to "Elegant","evergreen" to "Evergreen"),{format=it})
            for(key in listOf("logo","signature"))Section(friendly(key)){
                Surface(color=androidx.compose.ui.graphics.Color.White,shape=MaterialTheme.shapes.medium){if(values[key].isNullOrBlank())Box(Modifier.fillMaxWidth().height(100.dp),contentAlignment=androidx.compose.ui.Alignment.Center){Text("No ${friendly(key).lowercase()} uploaded",color=androidx.compose.ui.graphics.Color.DarkGray)}else DataImage(values[key]?:"",Modifier.fillMaxWidth().height(120.dp))}
                Text(if(key=="logo")"Logo uploads save immediately and appear on all document downloads."else"Save document details after choosing a signature.",style=MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){
                    OutlinedButton(enabled=vm.busy==0,onClick={vm.files.pick(arrayOf("image/*")){uri->vm.task{val value=vm.files.image(uri,900,240000);if(key=="logo")vm.api.request(vm.api.company(cid,"/document-branding"),"PATCH",JSONObject().put("logo",value));values[key]=value;if(key=="logo")vm.notice="Company logo saved. Reopen any document to see it."}}}){Text(if(key=="logo")"Upload & save logo"else"Upload signature")}
                    TextButton(enabled=vm.busy==0,onClick={vm.task{if(key=="logo")vm.api.request(vm.api.company(cid,"/document-branding"),"PATCH",JSONObject().put("logo",""));values[key]="";if(key=="logo")vm.notice="Company logo removed."}}){Text(if(key=="logo")"Remove saved logo"else"Remove")}
                }
            }
            for((key,label)in listOf("phone" to "Phone","email" to "Email","bank_name" to "Bank name","account_number" to "Account number","ifsc" to "IFSC","branch" to "Branch","upi_id" to "UPI ID","notes" to "Default notes","terms" to "Terms and conditions"))Field(label,values[key]?:"",{values[key]=it},multiline=key in setOf("notes","terms"),maximum=when(key){"phone"->32;"email"->254;"account_number"->64;"ifsc"->20;"notes"->1500;"terms"->3000;else->120})
        }
    }
}

@Composable fun MembersTool(vm:AppModel){val cid=vm.companyId;var email by remember{mutableStateOf("")};var role by remember{mutableStateOf("viewer")};var rows by remember{mutableStateOf(emptyList<JSONObject>())};var revision by remember{mutableIntStateOf(0)};var remove by remember{mutableStateOf<JSONObject?>(null)}
    LaunchedEffect(revision){try{rows=(vm.api.request(vm.api.company(cid,"/members"))as JSONArray).objects()}catch(e:Exception){vm.failure(e)}}
    ActionDialog("Company members",vm,confirm="Done",onSave={vm.tool=""},onDismiss={vm.tool=""}){Field("Registered user's email",email,{email=it},maximum=254);Choice("Role",role,listOf("viewer" to "Viewer","editor" to "Editor"),{role=it});Button(onClick={vm.task{vm.api.request(vm.api.company(cid,"/members"),"POST",JSONObject().put("email",email.trim()).put("role",role));email="";revision++}}){Text("Add / update access")};rows.forEach{row->Section{Text(row.s("email"));Text(friendly(row.s("role")));if(row.s("role")!="owner")TextButton(onClick={remove=row}){Text("Remove access")}}}}
    remove?.let{row->AlertDialog(onDismissRequest={remove=null},title={Text("Remove company access?")},text={Text("${row.s("email")} will no longer have access to this company.")},confirmButton={TextButton(onClick={vm.task{vm.api.request(vm.api.company(cid,"/members/${encode(row.s("email"))}"),"DELETE");remove=null;revision++}}){Text("Remove")}},dismissButton={TextButton(onClick={remove=null}){Text("Cancel")}})}
}
