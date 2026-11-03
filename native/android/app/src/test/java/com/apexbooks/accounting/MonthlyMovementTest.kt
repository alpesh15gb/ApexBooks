package com.apexbooks.accounting

import com.apexbooks.accounting.data.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.math.BigDecimal
import java.time.LocalDate
import java.time.format.DateTimeFormatter

class MonthlyMovementTest {
    // Previous chart algorithm, retained here as the exact-output oracle.
    private fun reference(records:List<JSONObject>,start:LocalDate,end:LocalDate)=
        generateSequence(start.withDayOfMonth(1)){it.plusMonths(1)}.takeWhile{!it.isAfter(end)}.take(13).map{month->
            val rows=records.filter{it.optBoolean("posted")&&it.s("date")>=start.toString()&&it.s("date")<=end.toString()&&it.s("date").startsWith(month.toString().take(7))}
            MonthMovement(month.format(DateTimeFormatter.ofPattern("MMM")),rows.fold(BigDecimal.ZERO){sum,r->sum+when(r.s("kind")){"sales_invoice","pos"->r.decimal("amount");"credit_note"->-r.decimal("amount");else->BigDecimal.ZERO}},rows.fold(BigDecimal.ZERO){sum,r->sum+when(r.s("kind")){"purchase_bill"->r.decimal("amount");"debit_note"->-r.decimal("amount");else->BigDecimal.ZERO}})
        }.toList()
    private fun row(date:String,kind:String,amount:String,posted:Boolean=true)=JSONObject().put("date",date).put("kind",kind).put("amount",amount).put("posted",posted)
    private fun equivalent(rows:List<JSONObject>,from:String,to:String){
        val start=LocalDate.parse(from);val end=LocalDate.parse(to)
        assertEquals(reference(rows,start,end),monthlyMovements(rows,start,end))
    }
    @Test fun mixedKindsBoundsSameDateAndDecimalScaleMatchPreviousFolds(){
        val rows=listOf(row("2026-04-10","sales_invoice","100.000"),row("2026-04-10","credit_note","20.01"),row("2026-04-10","pos","0.001"),row("2026-04-10","purchase_bill","50.00"),row("2026-04-10","debit_note","60.0000"),row("2026-04-10","expense","999.00"),row("2026-04-10","sales_invoice","999",false),row("2026-04-09","sales_invoice","999"),row("2026-05-21","sales_invoice","999"),row("2026-05-20","sales_invoice","1"))
        equivalent(rows,"2026-04-10","2026-05-20")
        val result=monthlyMovements(rows,LocalDate.parse("2026-04-10"),LocalDate.parse("2026-05-20"))
        assertEquals(BigDecimal("79.991"),result[0].sales)
        assertEquals(BigDecimal("-10.0000"),result[0].purchases)
    }
    @Test fun emptyInvertedYearBoundaryAndThirteenMonthCapMatch(){
        val rows=listOf(row("2025-12-31","sales_invoice","12"),row("2026-01-01","credit_note","2"),row("2027-02-01","sales_invoice","99"))
        equivalent(rows,"2025-12-31","2026-01-01")
        equivalent(rows,"2026-04-20","2026-04-10")
        equivalent(rows,"2026-05-01","2026-04-30")
        equivalent(emptyList(),"2026-04-01","2026-11-03")
        equivalent(rows,"2025-12-01","2027-12-31")
        assertEquals(13,monthlyMovements(rows,LocalDate.parse("2025-12-01"),LocalDate.parse("2027-12-31")).size)
    }
    @Test fun fiftyThousandMixedRecordsMatchWithoutMutatingInput(){
        val kinds=listOf("sales_invoice","pos","credit_note","purchase_bill","debit_note","expense","party","item")
        val rows=(0 until 50000).map{i->row(LocalDate.of(2026,i%12+1,i%28+1).toString(),kinds[i%kinds.size],BigDecimal(i%10000).movePointLeft(2).toPlainString(),i%7!=0)}
        val before=rows.map{it.toString()}
        equivalent(rows,"2026-04-01","2026-11-03")
        var visits=0
        val counted=object:AbstractList<JSONObject>(){
            override val size:Int get()=rows.size
            override fun get(index:Int):JSONObject{visits++;return rows[index]}
        }
        monthlyMovements(counted,LocalDate.parse("2026-04-01"),LocalDate.parse("2026-11-03"))
        assertEquals(50000,visits)
        assertEquals(before,rows.map{it.toString()})
    }
}
