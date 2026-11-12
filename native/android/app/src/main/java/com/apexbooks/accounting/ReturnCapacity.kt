package com.apexbooks.accounting

/** Quantity snapshot only; server amounts, tax and stock caps still apply. */
fun additionalReturnQuantity(scope:String,remaining:String):String =
    if(scope=="additional_returns" && remaining.toBigDecimalOrNull()?.let{it.signum()>=0}==true) remaining else ""
