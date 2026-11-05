package com.apexbooks.accounting

import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val ledgerDates = DateTimeFormatter.ofPattern("dd-MMM-yyyy", Locale.ENGLISH)

/** 2024-04-05 becomes 05-Apr-2024, as Tally writes dates. */
fun ledgerDate(iso: String): String = runCatching { LocalDate.parse(iso).format(ledgerDates) }.getOrDefault(iso)

/** Indian digit grouping with two decimals; a blank stays blank. */
fun ledgerAmount(value: String): String {
    val number = value.toBigDecimalOrNull() ?: return ""
    val parts = number.abs().setScale(2, RoundingMode.HALF_UP).toPlainString().split('.')
    var whole = parts[0]
    var grouped = whole.takeLast(3)
    whole = whole.dropLast(3)
    while (whole.isNotEmpty()) { grouped = whole.takeLast(2) + "," + grouped; whole = whole.dropLast(2) }
    return (if (number < BigDecimal.ZERO) "-" else "") + grouped + "." + parts[1]
}

fun ledgerBalance(amount: String, side: String): String = (ledgerAmount(amount.ifBlank { "0" }) + " " + side).trim()
