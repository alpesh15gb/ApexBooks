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
}
