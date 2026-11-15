package com.apexbooks.accounting

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.apexbooks.accounting.data.AmountPrivacy
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Asks for the account password and shows dashboard amounts only after the server confirms it. */
@Composable fun RevealAmountsDialog(vm: AppModel, onRevealed: () -> Unit, onDismiss: () -> Unit) {
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val focus = remember { FocusRequester() }
    // Focus the field on open and again after a failed attempt so the user can retype immediately.
    LaunchedEffect(Unit) { focus.requestFocus() }
    LaunchedEffect(error) { if (error.isNotEmpty()) runCatching { focus.requestFocus() } }
    fun submit() {
        if (busy) return
        if (password.isEmpty()) { error = "Enter your password to show amounts."; return }
        val attempt = password
        busy = true; error = ""
        scope.launch {
            try {
                vm.api.request("/api/auth/verify-password", "POST", JSONObject().put("password", attempt))
                password = ""
                onRevealed()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                password = ""
                if (AmountPrivacy.revealUnsupported(failure)) onRevealed()
                else { busy = false; error = AmountPrivacy.revealError(failure) }
            }
        }
    }
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Show amounts") },
        text = {
            Column {
                Text("Enter your account password to show the amounts on this dashboard.")
                OutlinedTextField(
                    value = password, onValueChange = { password = it; error = "" },
                    modifier = Modifier.fillMaxWidth().padding(top = 16.dp).focusRequester(focus), label = { Text("Password") },
                    singleLine = true, enabled = !busy, isError = error.isNotEmpty(),
                    supportingText = { if (error.isNotEmpty()) Text(error) },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { submit() }),
                )
            }
        },
        confirmButton = { Button(onClick = { submit() }, enabled = !busy) { Text(if (busy) "Checking…" else "Show amounts") } },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("Cancel") } },
    )
}
