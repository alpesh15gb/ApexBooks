package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApexApi
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.SocketException
import java.util.concurrent.Executors
import kotlin.concurrent.thread
import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CapabilityColdStartTest {
    @Test fun slowOptionalDiscoveryDoesNotBlockCoreRequest() = runBlocking {
        val executor=Executors.newFixedThreadPool(2)
        val server=ServerSocket().apply{bind(InetSocketAddress("127.0.0.1",0))}
        val worker=thread(isDaemon=true) {
            while(!server.isClosed) {
                val socket=try{server.accept()}catch(_:SocketException){break}
                executor.submit {
                    socket.use {
                        val reader=it.getInputStream().bufferedReader()
                        val path=reader.readLine().split(" ")[1]
                        while(!reader.readLine().isNullOrEmpty()){}
                        val body=if(path=="/api/capabilities") {
                            Thread.sleep(2100)
                            """{"api_version":"1.5.0","build_revision":"${"a".repeat(40)}","capabilities_version":1,"supported_features":["chunked_backups"]}"""
                        }else """{"status":"ok"}"""
                        val bytes=body.toByteArray()
                        it.getOutputStream().apply{write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n".toByteArray());write(bytes);flush()}
                    }
                }
            }
        }
        try {
            val api=ApexApi("http://127.0.0.1:${server.localPort}")
            val discovery=async { ApiCapabilities.fetchResult{api.request("/api/capabilities") as JSONObject} }
            val core=withTimeout(1500){api.request("/api/health") as JSONObject}
            assertEquals("ok",core.getString("status"))
            assertFalse("Optional discovery should remain independently pending",discovery.isCompleted)
            val result=withTimeout(6000){discovery.await()}
            assertFalse(result.retryable);assertTrue("chunked_backups" in result.features)
            assertEquals("1.5.0",result.apiVersion);assertEquals("a".repeat(40),result.buildRevision)
        } finally {server.close();worker.join(1000);executor.shutdownNow()}
    }
}
