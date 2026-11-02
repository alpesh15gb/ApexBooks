package com.apexbooks.accounting

import java.time.LocalDate

fun reportPeriod(mode:String,anchor:String,from:String,to:String):Pair<String,String>{
    if(mode=="custom"){
        val start=LocalDate.parse(from);val end=LocalDate.parse(to)
        require(!end.isBefore(start)){"The end date must be on or after the start date."}
        return start.toString() to end.toString()
    }
    val date=LocalDate.parse(anchor);val months=if(mode=="quarter")3L else 1L
    val start=date.withMonth(if(mode=="quarter")((date.monthValue-1)/3)*3+1 else date.monthValue).withDayOfMonth(1)
    return start.toString() to start.plusMonths(months).minusDays(1).toString()
}
