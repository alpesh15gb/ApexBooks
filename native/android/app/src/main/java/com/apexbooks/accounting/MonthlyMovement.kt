package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONObject
import java.math.BigDecimal
import java.time.LocalDate
import java.time.format.DateTimeFormatter

internal data class MonthMovement(val label:String,val sales:BigDecimal,val purchases:BigDecimal)

/** One traversal, preserving input addition order independently for each month. */
internal fun monthlyMovements(records:List<JSONObject>,start:LocalDate,end:LocalDate):List<MonthMovement>{
    val months=generateSequence(start.withDayOfMonth(1)){it.plusMonths(1)}
        .takeWhile{!it.isAfter(end)}.take(13).toList()
    if(months.isEmpty())return emptyList()
    val indices=months.mapIndexed{index,month->month.toString().take(7) to index}.toMap()
    val sales=Array(months.size){BigDecimal.ZERO}
    val purchases=Array(months.size){BigDecimal.ZERO}
    val from=start.toString();val to=end.toString()
    for(record in records){
        if(!record.optBoolean("posted"))continue
        val date=record.s("date")
        if(date<from||date>to)continue
        val index=indices[date.take(7)]?:continue
        // Retain the previous folds' zero additions and decimal scale semantics.
        val sale=when(record.s("kind")){"sales_invoice","pos"->record.decimal("amount");"credit_note"->-record.decimal("amount");else->BigDecimal.ZERO}
        val purchase=when(record.s("kind")){"purchase_bill"->record.decimal("amount");"debit_note"->-record.decimal("amount");else->BigDecimal.ZERO}
        sales[index]=sales[index]+sale;purchases[index]=purchases[index]+purchase
    }
    return months.mapIndexed{index,month->MonthMovement(month.format(DateTimeFormatter.ofPattern("MMM")),sales[index],purchases[index])}
}
