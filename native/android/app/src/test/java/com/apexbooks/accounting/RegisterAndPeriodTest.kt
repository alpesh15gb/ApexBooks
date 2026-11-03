package com.apexbooks.accounting

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RegisterAndPeriodTest {
    @Test fun dashboardUsesSameIndiaDayAsDocumentDefaults(){
        val instant=java.time.Instant.parse("2026-11-02T18:30:00Z")
        assertEquals(java.time.LocalDate.parse("2026-04-01") to java.time.LocalDate.parse("2026-11-03"),dashboardPeriod("year",instant))
        assertEquals(java.time.LocalDate.parse("2026-11-01") to java.time.LocalDate.parse("2026-11-03"),dashboardPeriod("month",instant))
        assertEquals(java.time.LocalDate.parse("2026-10-05") to java.time.LocalDate.parse("2026-11-03"),dashboardPeriod("30days",instant))
        assertEquals(java.time.LocalDate.parse("2027-04-01") to java.time.LocalDate.parse("2027-04-01"),dashboardPeriod("year",java.time.Instant.parse("2027-03-31T18:30:00Z")))
    }

    private fun row(id:String,date:String,amount:String,due:String,kind:String="sales_invoice")=JSONObject().put("id",id).put("kind",kind).put("name","Customer QA").put("number",id).put("date",date).put("amount",amount).put("outstanding",due).put("posted",true).put("data",JSONObject())
    @Test fun advancesAndCreditsHaveActionableBalanceStates(){
        val advance=row("advance","2026-11-01","100","0","payment_in").put("data",JSONObject().put("is_advance",true)).put("advance_remaining","40")
        assertEquals("Advance available",registerStatus(advance));advance.put("advance_remaining","0");assertEquals("Advance settled",registerStatus(advance))
        val credit=row("credit","2026-11-01","100","0","credit_note").put("credit_remaining","25")
        assertEquals("Credit available",registerStatus(credit));credit.put("credit_remaining","0");assertEquals("Credit settled",registerStatus(credit))
    }
    @Test fun inclusivePeriodAndServerBalances(){
        val rows=listOf(row("a","2026-10-01","100","100"),row("b","2026-10-31","100","40"),row("c","2026-11-01","100","0"),row("p","2026-10-15","30","30","purchase_bill"))
        val selected=filterRegister(rows,"sales_invoice","","2026-10-01","2026-10-31","all","all","old")
        assertEquals(listOf("a","b"),selected.map{it.getString("id")})
        assertEquals("Unpaid",registerStatus(rows[0]));assertEquals("Part settled",registerStatus(rows[1]));assertEquals("Settled",registerStatus(rows[2]))
        assertEquals(listOf("b"),filterRegister(rows,"sales_invoice","","","","Customer QA","Part settled","new").map{it.getString("id")})
    }
    @Test fun numericSortAndConvertedDraft(){
        val rows=listOf(row("small","2026-11-01","20.50","20.50"),row("big","2026-11-01","100","100"))
        assertEquals("big",filterRegister(rows,"sales_invoice","","","","all","all","amount").first().getString("id"))
        val draft=row("quote","2026-11-01","100","0","estimate").put("posted",false)
        assertEquals("Draft",registerStatus(draft));draft.put("converted_to","invoice-id");assertEquals("Converted",registerStatus(draft))
        val item=row("product","2020-01-01","0","0","item").put("data",JSONObject().put("barcode","QA-123"))
        assertEquals(1,filterRegister(listOf(item),"item","qa-123","2026-01-01","2026-12-31","all","all","new").size)
    }
    @Test fun sameDaySortUsesCreationMetadataRatherThanIdentifier(){
        val early=row("zz-early","2026-11-01","100","100").put("data",JSONObject().put("created_at","2026-11-01T08:00:00+00:00"))
        val late=row("aa-late","2026-11-01","100","100").put("data",JSONObject().put("created_at","2026-11-01T09:00:00+00:00"))
        val rows=listOf(early,late)
        assertEquals(listOf("aa-late","zz-early"),filterRegister(rows,"sales_invoice","","","","all","all","new").map{it.getString("id")})
        assertEquals(listOf("zz-early","aa-late"),filterRegister(rows,"sales_invoice","","","","all","all","old").map{it.getString("id")})
    }
    @Test fun gstMonthQuarterAndLeapYear(){
        assertEquals("2028-02-01" to "2028-02-29",reportPeriod("month","2028-02-17","",""))
        assertEquals("2026-10-01" to "2026-12-31",reportPeriod("quarter","2026-11-01","",""))
        assertEquals("2027-01-01" to "2027-03-31",reportPeriod("quarter","2027-03-31","",""))
        assertEquals("2026-10-01" to "2026-10-31",reportPeriod("custom","","2026-10-01","2026-10-31"))
    }
    @Test(expected=IllegalArgumentException::class) fun reversedPeriodRejected(){reportPeriod("custom","","2026-11-02","2026-11-01")}
}
