package com.apexbooks.accounting
import kotlinx.coroutines.CancellationException
suspend fun <T> scopedExternalAction(load:suspend()->String,current:()->Boolean,prepare:(String)->T,launch:(T)->Unit) {
    if(!current())return
    val value=try{load()}catch(e:CancellationException){throw e}catch(e:Exception){""}
    if(!current())return
    val payload=prepare(value)
    if(current())launch(payload)
}
