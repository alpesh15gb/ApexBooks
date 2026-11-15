package com.apexbooks.accounting

import org.json.JSONObject
import com.apexbooks.accounting.data.o
import com.apexbooks.accounting.data.s
import java.math.BigDecimal

internal fun exactPosMatches(products: List<JSONObject>, search: String, barcodeOnly: Boolean): List<JSONObject> {
    val value = search.trim()
    if (value.isEmpty()) return emptyList()
    val barcodes = products.filter { it.o("data").s("barcode") == value }
    return if (barcodes.isNotEmpty() || barcodeOnly) barcodes
    else products.filter { it.s("name").trim().equals(value, ignoreCase = true) }
}

internal fun posMoneyInput(value: String): BigDecimal? {
    val amount = value.trim().toBigDecimalOrNull() ?: return null
    return amount.takeIf { it.signum() >= 0 && it.scale() <= 2 && it <= BigDecimal("9999999999999.99") }
}

internal fun posCashDue(total: BigDecimal, method: String, bankAmount: String): BigDecimal? = when (method) {
    "cash" -> total
    "bank" -> BigDecimal.ZERO
    "split" -> posMoneyInput(bankAmount)?.takeIf { it.signum() > 0 && it < total }?.let { total - it }
    else -> null
}
