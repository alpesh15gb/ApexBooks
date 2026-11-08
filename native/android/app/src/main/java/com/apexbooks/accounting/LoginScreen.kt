package com.apexbooks.accounting

import androidx.compose.foundation.background
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.autofill.ContentType
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.contentType
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.*
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.net.URI

@Composable fun LoginScreen(vm:AppModel){
    var email by rememberSaveable{mutableStateOf("")}
    // Passwords remain in memory only and are never normalized or saved in instance state.
    var password by remember{mutableStateOf("")}
    var repeat by remember{mutableStateOf("")}
    var code by remember{mutableStateOf("")}
    var mode by rememberSaveable{mutableStateOf("login")}
    var keepSignedIn by rememberSaveable{mutableStateOf(false)}
    var submitting by remember{mutableStateOf(false)}
    val focus=LocalFocusManager.current
    val keyboard=LocalSoftwareKeyboardController.current
    val blocked=submitting||vm.busy>0
    fun submit(){
        if(submitting||vm.busy>0)return
        focus.clearFocus();keyboard?.hide()
        val sentEmail=email.trim()
        val sentPassword=password
        val sentRepeat=repeat
        val sentCode=code.trim()
        val sentMode=mode
        val rememberSession=keepSignedIn
        if(sentEmail.isBlank()||sentEmail.length>254){vm.error="Enter your account email address.";return}
        if(sentPassword.length !in 8..128){vm.error="Enter your complete password (8–128 characters).";return}
        if(sentMode=="register"&&sentPassword!=sentRepeat){vm.error="Passwords do not match.";return}
        if(sentMode=="recover"&&sentCode.isBlank()){vm.error="Enter a one-use recovery code.";return}
        submitting=true
        vm.task{
            try{
                when(sentMode){
                    "register"->{
                        vm.api.request("/api/auth/register","POST",JSONObject().put("email",sentEmail).put("password",sentPassword))
                        vm.login(sentEmail,sentPassword,false)
                    }
                    "recover"->{
                        vm.api.request("/api/auth/recover","POST",JSONObject().put("email",sentEmail).put("code",sentCode).put("new_password",sentPassword))
                        mode="login";code="";vm.notice="Password reset. Sign in with the new password."
                    }
                    else->vm.login(sentEmail,sentPassword,rememberSession)
                }
                password="";repeat=""
            }finally{submitting=false}
        }
    }
    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color(0xFFFFE9D4),MaterialTheme.colorScheme.background))).safeDrawingPadding().imePadding(),contentAlignment=Alignment.Center){
        Column(Modifier.widthIn(max=460.dp).fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp),verticalArrangement=Arrangement.spacedBy(18.dp)){
            AppLogo(Modifier.fillMaxWidth())
            Heading(when(mode){"register"->"Create your account";"recover"->"Recover account access";else->"Your business, in balance."},"Your documents, balances and settings across every device.")
            Message(vm.error,true){vm.error=""}
            CredentialField("Email address",email,{email=it},!blocked,false,if(mode=="register")ContentType.NewUsername else ContentType.Username,ImeAction.Next,{focus.moveFocus(androidx.compose.ui.focus.FocusDirection.Next)})
            if(mode=="recover")CredentialField("One-use recovery code",code,{code=it},!blocked,false,null,ImeAction.Next,{focus.moveFocus(androidx.compose.ui.focus.FocusDirection.Next)})
            CredentialField(if(mode=="recover")"New password"else"Password",password,{password=it},!blocked,true,if(mode=="login")ContentType.Password else ContentType.NewPassword,if(mode=="register")ImeAction.Next else ImeAction.Done,{if(mode=="register")focus.moveFocus(androidx.compose.ui.focus.FocusDirection.Next)else submit()})
            if(mode=="register")CredentialField("Confirm password",repeat,{repeat=it},!blocked,true,ContentType.NewPassword,ImeAction.Done,{submit()})
            if(mode=="login")Toggle("Keep me signed in on this device",keepSignedIn,{keepSignedIn=it},enabled=!blocked)
            Button(enabled=!blocked,onClick={submit()},modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)){
                if(blocked)CircularProgressIndicator(Modifier.size(20.dp),strokeWidth=2.dp,color=MaterialTheme.colorScheme.onPrimary)
                else Text(when(mode){"register"->"Create account";"recover"->"Reset access";else->"Sign in"})
            }
            TextButton(enabled=!blocked,onClick={mode=if(mode=="login")"register"else"login";password="";repeat="";code="";vm.error=""}){Text(if(mode=="login")"Create an account"else"Back to sign in")}
            if(mode=="login")TextButton(enabled=!blocked,onClick={mode="recover";password="";repeat="";vm.error=""}){Text("Use a recovery code")}
            Text("${if(BuildConfig.DEBUG)"Apex Books Dev"else"Apex Books"} ${BuildConfig.VERSION_NAME} · ${URI(vm.api.origin).host}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable private fun CredentialField(label:String,value:String,onChange:(String)->Unit,enabled:Boolean,password:Boolean,type:ContentType?,action:ImeAction,onAction:()->Unit){
    var visible by remember{mutableStateOf(false)}
    OutlinedTextField(value=value,onValueChange=onChange,enabled=enabled,shape=RoundedCornerShape(14.dp),colors=OutlinedTextFieldDefaults.colors(unfocusedContainerColor=Color.White,focusedContainerColor=Color.White),label={Text(label)},singleLine=true,
        modifier=Modifier.fillMaxWidth().semantics{if(type!=null)contentType=type},
        keyboardOptions=KeyboardOptions(capitalization=KeyboardCapitalization.None,autoCorrectEnabled=false,keyboardType=if(password)KeyboardType.Password else if(label=="Email address")KeyboardType.Email else KeyboardType.Ascii,imeAction=action),
        keyboardActions=KeyboardActions(onNext={onAction()},onDone={onAction()}),
        visualTransformation=if(password&&!visible)PasswordVisualTransformation()else VisualTransformation.None,
        trailingIcon=if(password){{IconButton(enabled=enabled,onClick={visible=!visible}){Icon(if(visible)Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility,if(visible)"Hide password"else"Show password")}}}else null)
}
