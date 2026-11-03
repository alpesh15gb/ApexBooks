package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApexApi
import java.net.ServerSocket
import kotlin.concurrent.thread
import java.net.InetSocketAddress
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import kotlin.system.measureTimeMillis

class CompanyLoadTest {
    @Test fun compactPagingLoadsAllRecordsWithFewerRoundTrips() = runBlocking {
        val calls=AtomicInteger()
        val server=ServerSocket();server.bind(InetSocketAddress("127.0.0.1",0))
        val worker=thread(isDaemon=true) { while(!server.isClosed) { val socket=try{server.accept()}catch(_:java.net.SocketException){break};socket.use {
            val reader=it.getInputStream().bufferedReader();val path=reader.readLine().split(" ")[1];while(!reader.readLine().isNullOrEmpty()){}
            calls.incrementAndGet(); Thread.sleep(20)
            val query=path.substringAfter("?").split("&").associate { val pair=it.split("=");pair[0] to pair[1] }
            val offset=query.getValue("offset").toInt();val limit=query.getValue("limit").toInt()
            val rows=JSONArray();for(i in offset until minOf(offset+limit,1250))rows.put(JSONObject().put("id","row-$i").put("kind","party").put("name","Synthetic $i"))
            val body=rows.toString().toByteArray();it.getOutputStream().apply{write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${body.size}\r\nConnection: close\r\n\r\n".toByteArray());write(body);flush()}
        } } }
        try {
            val api=ApexApi("http://127.0.0.1:${server.localPort}")
            val baseline=measureTimeMillis { for(offset in 0..1200 step 100)api.request(api.company("test","/records?compact=true&limit=100&offset=$offset")) }
            assertEquals(13,calls.get());calls.set(0)
            val improved=measureTimeMillis { val rows=api.records("test");assertEquals(1250,rows.size);assertEquals(1250,rows.map{it.getString("id")}.toSet().size) }
            assertEquals(3,calls.get())
            println("COMPANY_LOAD_SYNTHETIC rows=1250 latency=20ms old_requests=13 new_requests=3 old_ms=$baseline new_ms=$improved")
        } finally { server.close();worker.join(1000) }
    }
    private fun scanPages(pages:List<List<String>>, verify:(List<JSONObject>?,Throwable?,List<Int>)->Unit) = runBlocking {
        val offsets=java.util.Collections.synchronizedList(mutableListOf<Int>())
        val server=ServerSocket();server.bind(InetSocketAddress("127.0.0.1",0))
        val worker=thread(isDaemon=true) {
            while(!server.isClosed){
                val socket=try{server.accept()}catch(_:java.net.SocketException){break}
                socket.use {
                    val reader=it.getInputStream().bufferedReader();val path=reader.readLine().split(" ")[1]
                    while(!reader.readLine().isNullOrEmpty()){}
                    val offset=path.substringAfter("offset=").toInt()
                    val ids=pages.getOrElse(offsets.size){emptyList()};offsets.add(offset)
                    val rows=JSONArray();ids.forEach{id->rows.put(JSONObject().put("id",id).put("kind","invoice"))}
                    val body=rows.toString().toByteArray()
                    it.getOutputStream().apply{write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${body.size}\r\nConnection: close\r\n\r\n".toByteArray());write(body);flush()}
                }
            }
        }
        try {
            val result=runCatching{ApexApi("http://127.0.0.1:${server.localPort}").records("test")}
            verify(result.getOrNull(),result.exceptionOrNull(),offsets.toList())
        } finally {server.close();worker.join(1000)}
    }
    @Test fun insertionBetweenPagesDiscardsScanAndRestartsOnce(){
        val original=(0..999).map{"row-$it"};val changed=listOf("new-row")+original
        scanPages(listOf(original.take(500),changed.drop(500).take(500),changed.take(500),changed.drop(500).take(500),changed.drop(1000))){rows,error,offsets->
            assertNull(error);assertEquals(changed,rows!!.map{it.getString("id")})
            assertEquals(listOf(0,500,0,500,1000),offsets)
        }
    }
    @Test fun repeatedOverlapFailsWithoutReturningPartialHistory(){
        val first=(0..499).map{"row-$it"};val overlap=listOf("row-499")+(500..998).map{"row-$it"}
        scanPages(listOf(first,overlap,first,overlap)){rows,error,offsets->
            assertNull(rows);assertTrue(error is com.apexbooks.accounting.data.ApiFailure)
            assertTrue(error!!.message!!.contains("Refresh"));assertEquals(listOf(0,500,0,500),offsets)
        }
    }
    @Test fun duplicateWithinShortPageAlsoFailsClosed(){
        scanPages(listOf(listOf("same","same"),listOf("same","same"))){rows,error,offsets->
            assertNull(rows);assertNotNull(error);assertEquals(listOf(0,0),offsets)
        }
    }

}
