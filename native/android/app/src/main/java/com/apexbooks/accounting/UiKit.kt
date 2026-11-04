@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.apexbooks.accounting

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.*
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.apexbooks.accounting.data.*
import org.json.JSONArray
import org.json.JSONObject
import java.time.*

val ApexGreen=Color(0xFF1B3C73) // Ledger Navy primary (name kept for existing call sites)
val ApexInk=Color(0xFF0F1D36)
val ApexNavy=Color(0xFF0D2142)
private val WorkspaceFont=FontFamily(Font(R.font.dm_sans_regular,FontWeight.Normal),Font(R.font.dm_sans_medium,FontWeight.Medium),Font(R.font.dm_sans_semibold,FontWeight.SemiBold),Font(R.font.dm_sans_bold,FontWeight.Bold))
private val WorkspaceType=Typography().let{base->Typography(
    displayLarge=base.displayLarge.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont),displayMedium=base.displayMedium.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont),displaySmall=base.displaySmall.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont),
    headlineLarge=base.headlineLarge.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=28.sp),headlineMedium=base.headlineMedium.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=24.sp),headlineSmall=base.headlineSmall.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=22.sp),
    titleLarge=base.titleLarge.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=20.sp),titleMedium=base.titleMedium.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=15.sp),titleSmall=base.titleSmall.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=13.sp),
    bodyLarge=base.bodyLarge.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=16.sp,lineHeight=24.sp),bodyMedium=base.bodyMedium.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=16.sp,lineHeight=24.sp),bodySmall=base.bodySmall.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=12.sp,lineHeight=18.sp),
    labelLarge=base.labelLarge.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=13.sp),labelMedium=base.labelMedium.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=11.sp),labelSmall=base.labelSmall.copy(fontFeatureSettings="tnum",fontFamily=WorkspaceFont,fontSize=11.sp))}
@Composable fun ApexTheme(content:@Composable ()->Unit){MaterialTheme(typography=WorkspaceType,colorScheme=lightColorScheme(primary=ApexGreen,onPrimary=Color.White,primaryContainer=Color(0xFFDCE5F5),onPrimaryContainer=Color(0xFF132C57),secondary=ApexGreen,onSecondary=Color.White,secondaryContainer=Color(0xFFEEF2FA),onSecondaryContainer=Color(0xFF132C57),background=Color(0xFFF4F6FA),onBackground=ApexInk,surface=Color.White,onSurface=ApexInk,surfaceVariant=Color(0xFFEEF2FA),onSurfaceVariant=Color(0xFF5B6B85),outline=Color(0xFFC4CEE0),outlineVariant=Color(0xFFDDE3EE),surfaceContainerLowest=Color.White,surfaceContainerLow=Color(0xFFF7F9FD),surfaceContainer=Color(0xFFEEF2FA),surfaceContainerHigh=Color(0xFFE4EAF5),surfaceContainerHighest=Color(0xFFDCE5F5)),shapes=Shapes(small=RoundedCornerShape(8.dp),medium=RoundedCornerShape(12.dp),large=RoundedCornerShape(16.dp),extraLarge=RoundedCornerShape(20.dp)),content=content)}
@Composable fun NumberedHeading(number:String,title:String,detail:String=""){Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)){Surface(color=Color(0xFFEAF2FF),border=BorderStroke(1.dp,Color(0xFFD8E6FA)),shape=RoundedCornerShape(8.dp)){Box(Modifier.size(30.dp),contentAlignment=Alignment.Center){Text(number,color=ApexGreen,style=MaterialTheme.typography.labelMedium,fontWeight=FontWeight.SemiBold)}};Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(3.dp)){Text(title,style=MaterialTheme.typography.titleSmall,fontWeight=FontWeight.SemiBold);if(detail.isNotBlank())Text(detail,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}}}
private fun sectionNumber(title:String)=title.substringBefore(' ').takeIf{it.length==2&&it.all(Char::isDigit)}
@Composable fun Heading(title:String,detail:String=""){val number=sectionNumber(title);if(number!=null)NumberedHeading(number,title.drop(2).trim(),detail)else Column(verticalArrangement=Arrangement.spacedBy(5.dp)){Text(title,style=MaterialTheme.typography.headlineSmall,fontWeight=FontWeight.SemiBold);if(detail.isNotBlank())Text(detail,style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
@Composable fun Section(title:String="",content:@Composable ColumnScope.()->Unit){Card(Modifier.fillMaxWidth(),shape=RoundedCornerShape(20.dp),colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surface)){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){if(title.isNotBlank()){val number=sectionNumber(title);if(number!=null)NumberedHeading(number,title.drop(2).trim())else Text(title,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.SemiBold)};content()}}}
@Composable fun Field(label:String,value:String,onChange:(String)->Unit,modifier:Modifier=Modifier,multiline:Boolean=false,number:Boolean=false,password:Boolean=false,readOnly:Boolean=false,maximum:Int=2000){var visible by remember{mutableStateOf(false)};OutlinedTextField(value,shape=RoundedCornerShape(14.dp),onValueChange={if(it.length<=maximum)onChange(it)},label={Text(label)},modifier=modifier.fillMaxWidth(),singleLine=!multiline,minLines=if(multiline)3 else 1,readOnly=readOnly,keyboardOptions=KeyboardOptions(keyboardType=when{password->KeyboardType.Password;number->KeyboardType.Decimal;label.contains("phone",true)->KeyboardType.Phone;label.contains("email",true)->KeyboardType.Email;else->KeyboardType.Text}),visualTransformation=if(password&&!visible)PasswordVisualTransformation()else VisualTransformation.None,trailingIcon=if(password){{IconButton(onClick={visible=!visible}){Icon(if(visible)Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility,if(visible)"Hide password" else "Show password")}}}else null)}
@Composable fun Toggle(label:String,checked:Boolean,onChange:(Boolean)->Unit,enabled:Boolean=true){Row(Modifier.fillMaxWidth().clickable(enabled=enabled){onChange(!checked)},verticalAlignment=Alignment.CenterVertically){Checkbox(checked,onCheckedChange=onChange,enabled=enabled);Text(label,Modifier.weight(1f),style=MaterialTheme.typography.bodyMedium)}}
fun selectionDescription(label:String,value:String)="$label · ${value.ifBlank{"Not set"}}"

@Composable fun Choice(label:String,value:String,options:List<Pair<String,String>>,onChange:(String)->Unit,modifier:Modifier=Modifier,enabled:Boolean=true){
    var opened by remember{mutableStateOf(false)};var search by remember{mutableStateOf("")}
    val displayed=options.find{it.first==value}?.second?:"Choose"
    Box(modifier.fillMaxWidth()){
        OutlinedTextField(displayed,{},label={Text(label)},readOnly=true,enabled=enabled,shape=RoundedCornerShape(14.dp),modifier=Modifier.fillMaxWidth().clearAndSetSemantics{},trailingIcon={Icon(Icons.Outlined.ExpandMore,null)})
        Box(Modifier.matchParentSize().semantics{contentDescription=selectionDescription(label,displayed)}.clickable(enabled=enabled,role=Role.Button,onClickLabel="Choose $label"){search="";opened=true})
    }
    if(opened)ModalBottomSheet(onDismissRequest={opened=false}){
        Column(Modifier.fillMaxWidth().padding(horizontal=20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){
            Heading(label)
            if(options.size>6)SearchBarField("Search options",search){search=it}
            val shown=options.filter{it.second.contains(search,true)}
            LazyColumn(Modifier.heightIn(max=440.dp)){
                if(shown.isEmpty())item{Text("No matching options",Modifier.padding(vertical=24.dp))}
                items(shown,key={it.first}){option->
                    ListItem(headlineContent={Text(option.second)},trailingContent={if(value==option.first)Icon(Icons.Outlined.CheckCircle,"Selected",tint=ApexGreen)},modifier=Modifier.clickable{if(enabled){onChange(option.first);opened=false}}.heightIn(min=56.dp))
                }
            }
            TextButton(onClick={opened=false},modifier=Modifier.fillMaxWidth()){Text("Cancel")}
            Spacer(Modifier.height(16.dp))
        }
    }
}
@Composable fun DateField(label:String,value:String,onChange:(String)->Unit,optional:Boolean=false){var opened by remember{mutableStateOf(false)};Box(Modifier.fillMaxWidth()){OutlinedTextField(value,{},label={Text(label)},readOnly=true,modifier=Modifier.fillMaxWidth().clearAndSetSemantics{},trailingIcon={Icon(Icons.Outlined.CalendarMonth,null)});Box(Modifier.matchParentSize().semantics{contentDescription=selectionDescription(label,value)}.clickable(role=Role.Button,onClickLabel="Choose $label"){opened=true})};if(opened){val state=rememberDatePickerState(initialSelectedDateMillis=runCatching{LocalDate.parse(value).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()}.getOrNull(),yearRange=2000..2100);DatePickerDialog(onDismissRequest={opened=false},confirmButton={TextButton(enabled=state.selectedDateMillis!=null,onClick={state.selectedDateMillis?.let{onChange(Instant.ofEpochMilli(it).atOffset(ZoneOffset.UTC).toLocalDate().toString())};opened=false}){Text("Select")}},dismissButton={Row{if(optional)TextButton(onClick={onChange("");opened=false}){Text("Clear")};TextButton(onClick={opened=false}){Text("Cancel")}}}){DatePicker(state)}}}
@Composable fun Message(text:String,error:Boolean=false,onDismiss:(()->Unit)?=null){if(text.isBlank())return;Surface(color=if(error)MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.primaryContainer,shape=RoundedCornerShape(12.dp)){Row(Modifier.padding(12.dp),verticalAlignment=Alignment.CenterVertically){Icon(if(error)Icons.Outlined.ErrorOutline else Icons.Outlined.CheckCircle,null,Modifier.padding(end=9.dp));Text(text,Modifier.weight(1f),style=MaterialTheme.typography.bodyMedium);if(onDismiss!=null)IconButton(onClick=onDismiss){Icon(Icons.Outlined.Close,"Dismiss")}}}}
@Composable fun Metric(label:String,value:String,modifier:Modifier=Modifier){Card(modifier,colors=CardDefaults.cardColors(containerColor=MaterialTheme.colorScheme.surface),shape=RoundedCornerShape(12.dp),border=BorderStroke(1.dp,MaterialTheme.colorScheme.outlineVariant)){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){Text(label,style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(value,style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.SemiBold,color=ApexInk)}}}
@Composable fun DataImage(url:String,modifier:Modifier=Modifier){val bitmap=remember(url){runCatching{val bytes=Base64.decode(url.substringAfter(','),Base64.DEFAULT);BitmapFactory.decodeByteArray(bytes,0,bytes.size)?.asImageBitmap()}.getOrNull()};if(bitmap!=null)Image(bitmap,null,modifier=modifier)else Box(modifier.background(MaterialTheme.colorScheme.surfaceVariant,RoundedCornerShape(12.dp)),contentAlignment=Alignment.Center){Icon(Icons.Outlined.Inventory2,null,tint=ApexGreen)}}

fun display(key:String,value:Any?):String {if(value==null||value==JSONObject.NULL)return "—";if(value is Boolean)return if(value)"Yes"else"No";val text=value.toString();if(key in setOf("kind","tax_mode","payment_account","payment_method","status","direction","category"))return friendly(text);if(key.contains("gst_rate")||key.contains("percent")||key.contains("tax_rate"))return "$text%";val decimal=text.toBigDecimalOrNull();return if(decimal!=null&&!listOf("quantity","count","records","items").any{key.contains(it)}&&((key in setOf("sales","purchases","receipts","payments","movement")||key.endsWith("_movement"))||listOf("amount","total","taxable","cgst","sgst","igst","value","balance","receivable","payable","profit","income","expense","debit","credit","cost","available","paid","outstanding","difference").any{key.contains(it)}))money(decimal)else text}
@Composable fun ReportContent(value:Any?,heading:String="") {
    when(value){
        is JSONObject->{val keys=value.keys().asSequence().toList();val simple=keys.filter{value.opt(it)!is JSONObject&&value.opt(it)!is JSONArray&&it!="id"&&it!="digest"&&!it.endsWith("_id")};if(simple.isNotEmpty())Section(heading){for(key in simple)Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(friendly(key),Modifier.weight(1f),style=MaterialTheme.typography.bodyMedium);Text(display(key,value.opt(key)),Modifier.weight(1f),fontWeight=FontWeight.Medium,style=MaterialTheme.typography.bodyMedium)}};for(key in keys.filter{value.opt(it)is JSONObject||value.opt(it)is JSONArray})ReportContent(value.opt(key),friendly(key))}
        is JSONArray->{
            if(value.length()==0){if(heading.isNotBlank())Section(heading){Text("No entries in this view.")};return}
            var page by remember(value){mutableIntStateOf(0)}
            val objects=remember(value){value.objects()}
            if(objects.isEmpty()){
                Section(heading){
                    for(i in page*50 until minOf((page+1)*50,value.length()))Text(value.opt(i).toString())
                    ReportPaging(page,value.length()){page=it}
                }
                return
            }
            val keys=remember(value){objects.flatMap{it.keys().asSequence().toList()}.distinct().filter{k->k!="id"&&k!="digest"&&!k.endsWith("_id")&&objects.any{it.opt(k)!is JSONObject&&it.opt(k)!is JSONArray&&it.has(k)}}}
            Section(heading){
                Row(Modifier.horizontalScroll(rememberScrollState())){
                    Column{
                        Row{keys.forEach{Text(friendly(it),Modifier.width(155.dp).padding(8.dp),fontWeight=FontWeight.SemiBold,style=MaterialTheme.typography.labelMedium)}}
                        objects.drop(page*50).take(50).forEach{row->
                            HorizontalDivider()
                            Row{keys.forEach{key->Text(display(key,row.opt(key)),Modifier.width(155.dp).padding(8.dp),style=MaterialTheme.typography.bodySmall)}}
                        }
                    }
                }
                ReportPaging(page,objects.size){page=it}
            }
        }
    }
}
@Composable private fun ReportPaging(page:Int,total:Int,onChange:(Int)->Unit){
    if(total<=50)return
    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.SpaceBetween){
        TextButton(enabled=page>0,onClick={onChange(page-1)}){Text("Previous")}
        Text("${page*50+1}–${minOf((page+1)*50,total)} of $total",style=MaterialTheme.typography.labelMedium)
        TextButton(enabled=(page+1)*50<total,onClick={onChange(page+1)}){Text("Next")}
    }
}
@Composable
fun ActionDialog(
    title: String,
    vm: AppModel,
    confirm: String = "Save",
    enabled: Boolean = true,
    hasChanges: () -> Boolean = { false },
    unresolved: () -> Boolean = { false },
    working: () -> Boolean = { false },
    onSave: suspend () -> Unit,
    onDismiss: () -> Unit,
    content: @Composable ColumnScope.() -> Unit
) {
    var saving by remember { mutableStateOf(false) }
    var discard by remember { mutableStateOf(false) }
    fun close(){if(!saving&&!working()){if(unresolved()){discard=false;vm.error="The previous save may already have posted. Retry the original save to recover its outcome before closing."}else if(hasChanges())discard=true else onDismiss()}}
    Dialog(
        onDismissRequest = { close() },
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        BoxWithConstraints(
            Modifier.fillMaxWidth().imePadding().padding(horizontal = 12.dp),
            contentAlignment = Alignment.Center
        ) {
            Surface(
                Modifier.widthIn(max = 900.dp).fillMaxWidth().heightIn(max = maxHeight * .95f),
                shape = RoundedCornerShape(22.dp),
                color = MaterialTheme.colorScheme.background
            ) {
                Column {
                    Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(title, Modifier.weight(1f), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                        IconButton(enabled = !saving&&!working(), onClick = { close() }) { Icon(Icons.Outlined.Close, "Close") }
                    }
                    Column(
                        Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()).padding(horizontal = 18.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        content()
                        Spacer(Modifier.height(18.dp))
                    }
                    Surface(shadowElevation = 4.dp) {
                        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Message(vm.error, true) { vm.error = "" }
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp, Alignment.End)) {
                                TextButton(enabled = !saving&&!working(), onClick = { close() }) { Text("Cancel") }
                                Button(
                                    enabled = enabled && !saving && !working() && vm.busy == 0,
                                    onClick = { saving = true; vm.task { try { onSave() } finally { saving = false } } }
                                ) {
                                    if (saving) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp) else Text(confirm)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    if(discard && !unresolved())AlertDialog(onDismissRequest={discard=false},title={Text("Discard unsaved changes?")},text={Text("These changes have not been saved. Keep editing or discard them.")},confirmButton={TextButton(onClick={discard=false;onDismiss()}){Text("Discard changes")}},dismissButton={TextButton(onClick={discard=false}){Text("Keep editing")}})

}
