package com.apexbooks.accounting

import com.apexbooks.accounting.data.Csv
import org.junit.Assert.*
import org.junit.Test

class CsvIntegrityTest {
    private fun rejects(message:String,action:()->Unit){try{action()}catch(e:Exception){assertTrue(e.message.orEmpty(),e.message.orEmpty().contains(message));return};fail("Expected rejection: $message")}
    @Test fun quotedNewlinesEscapesBomAndLeadingZerosRemainIntact(){
        val rows=Csv.parse(Csv.decode("\uFEFFname,phone\r\n\"A, B\n\"\"quoted\"\"\",00123\r\n".toByteArray(Charsets.UTF_8)))
        assertEquals("name",rows[0][0]);assertEquals("A, B\n\"quoted\"",rows[1][0]);assertEquals("00123",rows[1][1])
    }
    @Test fun malformedQuotesAndEncodingReject(){
        rejects("row 2"){Csv.parse("name\n\"A\"junk")};rejects("row 2"){Csv.parse("name\nA\"B")};rejects("unclosed"){Csv.parse("name\n\"A")}
        rejects("UTF-8"){Csv.decode(byteArrayOf(0x41,0x96.toByte(),0x42))}
    }
    @Test fun populatedUnmappedColumnsAndDuplicateHeadersReject(){
        val supported=setOf("name","phone")
        for(input in listOf("name,,phone\nA,lost data,00123","name,phone\nA,00123,extra","name,unknown\nA,lost","name,name\nA,B")){
            val rows=Csv.parse(input);rejects(if(input.startsWith("name,name"))"unique"else"row 2"){Csv.validateColumns(rows,rows[0],supported)}
        }
        val blank=Csv.parse("name,,phone\nA,,00123");Csv.validateColumns(blank,blank[0],supported)
    }
    @Test fun invalidStockFlagDoesNotSilentlyBecomeFalse(){assertTrue(Csv.boolean("YES"));assertFalse(Csv.boolean("no"));rejects("track_stock"){Csv.boolean("perhaps")}}
}
