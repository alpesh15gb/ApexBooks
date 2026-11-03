package com.apexbooks.accounting.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.text.NumberFormat
import java.time.LocalDate
import java.util.Locale

fun JSONObject.s(key: String): String = if (isNull(key)) "" else optString(key, "")
fun JSONObject.o(key: String): JSONObject = optJSONObject(key) ?: JSONObject()
fun JSONObject.a(key: String): JSONArray = optJSONArray(key) ?: JSONArray()
fun JSONArray.objects(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }
fun JSONObject.decimal(key: String): BigDecimal = s(key).toBigDecimalOrNull() ?: BigDecimal.ZERO
fun money(value: BigDecimal): String = NumberFormat.getCurrencyInstance(Locale.forLanguageTag("en-IN")).format(value)
fun money(value: String): String = money(value.toBigDecimalOrNull() ?: BigDecimal.ZERO)
fun copy(value: JSONObject): JSONObject = JSONObject(value.toString())
fun businessDate(instant:java.time.Instant=java.time.Instant.now()):LocalDate=instant.atOffset(java.time.ZoneOffset.ofHoursMinutes(5,30)).toLocalDate()
fun today(): String = businessDate().toString()
fun financialStart(): String = businessDate().let { "${if (it.monthValue >= 4) it.year else it.year - 1}-04-01" }
fun encode(value: String): String = URLEncoder.encode(value, "UTF-8")

class ApiFailure(val status: Int, message: String) : Exception(message)

/** All accounting is posted by the shared API. This client holds no database or AI-provider keys. */
class ApexApi(val origin: String = PRODUCTION, private val vault: SessionVault? = null) {
    init { val uri=java.net.URI(origin);require(uri.userInfo==null&&uri.rawQuery==null&&uri.fragment==null&&(uri.scheme=="https"||com.apexbooks.accounting.BuildConfig.DEBUG&&uri.scheme=="http"&&uri.host in setOf("10.0.2.2","127.0.0.1","localhost","::1"))) { "Use an HTTPS server address." } }
    companion object { const val PRODUCTION = "https://api.apexbooks.in" }
    var email: String = ""; private set
    private val sessionLock=Any()
    private var loginSequence=0
    @Volatile private var token: String = ""
    val signedIn: Boolean get() = token.isNotEmpty()

    fun restore(): Boolean {
        val saved = vault?.load(origin) ?: return false
        email = saved.s("email"); token = saved.s("token"); return signedIn
    }

    suspend fun login(emailAddress: String, password: String, remember: Boolean) {
        val attempt=synchronized(sessionLock){++loginSequence}
        val result = request("/api/auth/login", "POST", JSONObject().put("email", emailAddress.trim()).put("password", password)) as JSONObject
        val session = result.s("token"); if (session.isBlank()) throw ApiFailure(502, "The server did not return a sign-in session.")
        withContext(Dispatchers.IO){synchronized(sessionLock){if(attempt!=loginSequence)throw kotlinx.coroutines.CancellationException("Sign-in was cancelled.");vault?.clear(origin);token=session;email=emailAddress.trim();if(remember)vault?.save(origin,JSONObject().put("email",email).put("token",token))}}
    }

    suspend fun logout() {val sentToken=token;try { request("/api/auth/logout", "POST") } finally {invalidate(sentToken)} }
    fun forget() {synchronized(sessionLock){loginSequence++;token="";email="";vault?.clear(origin)}}
    private fun invalidate(sentToken:String):Boolean=synchronized(sessionLock){if(sentToken.isBlank()||token!=sentToken)false else{forget();true}}
    fun company(id: String, suffix: String = ""): String = "/api/companies/${encode(id)}$suffix"

    suspend fun request(path: String, method: String = "GET", body: JSONObject? = null, retryKey: String? = null): Any {
        val bytes = bytes(path, method, body, retryKey)
        if (bytes.isEmpty()) return JSONObject()
        return withContext(Dispatchers.Default) {
            val text = bytes.toString(Charsets.UTF_8)
            if (text.trimStart().startsWith("[")) JSONArray(text) else JSONObject(text)
        }
    }

    suspend fun bytes(path: String, method: String = "GET", body: JSONObject? = null, retryKey: String? = null): ByteArray = transfer(path,method,body?.toString()?.toByteArray(Charsets.UTF_8),retryKey,"application/json",null)
    suspend fun rawBytes(path:String,method:String="GET",content:ByteArray?=null,contentType:String="application/octet-stream",retryKey:String?=null,maximumResponse:Int=3_000_000):ByteArray=transfer(path,method,content,retryKey,contentType,maximumResponse)
    suspend fun upload(path:String,method:String,content:ByteArray,contentType:String,retryKey:String?=null):JSONObject {val result=rawBytes(path,method,content,contentType,retryKey);return withContext(Dispatchers.Default){JSONObject(result.toString(Charsets.UTF_8))}}
    private suspend fun transfer(path:String,method:String,body:ByteArray?,retryKey:String?,contentType:String,maximumResponse:Int?):ByteArray {
      val sentToken=token
      return withContext(Dispatchers.IO) {
        val connection = URL(origin.trimEnd('/') + "/" + path.trimStart('/')).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method; connection.instanceFollowRedirects=false
            // Optional compatibility discovery must not hold company startup behind the financial-write timeout.
            val capabilityProbe=method=="GET"&&path=="/api/capabilities"
            connection.connectTimeout = if(capabilityProbe)8000 else 20_000; connection.readTimeout = if(capabilityProbe)8000 else 90_000
            connection.setRequestProperty("Accept", "application/json"); connection.setRequestProperty("User-Agent", "ApexBooks-Android/${com.apexbooks.accounting.BuildConfig.VERSION_NAME}")
            if (sentToken.isNotBlank()) connection.setRequestProperty("Authorization", "Bearer $sentToken")
            if (retryKey != null) connection.setRequestProperty("Idempotency-Key", retryKey)
            if (body != null) { connection.doOutput = true; connection.setRequestProperty("Content-Type", contentType);connection.setFixedLengthStreamingMode(body.size); connection.outputStream.use { it.write(body) } }
            val code = connection.responseCode
            if (code !in 200..299) {
                val detail = connection.errorStream?.bufferedReader()?.use { it.readText() } ?: ""
                val message = runCatching { val value = JSONObject(detail).opt("detail"); if (value is JSONArray) value.objects().joinToString("\n") { it.s("msg") } else value?.toString() }.getOrNull() ?: "The request could not be completed."
                val challenge=path.substringBefore('?') in setOf("/api/auth/login","/api/auth/change-password","/api/auth/recovery-codes")
                val expired=code==401&&!challenge&&invalidate(sentToken)
                throw ApiFailure(code, if (expired) "Your session has ended. Sign in again." else message)
            }
            connection.inputStream.use { input -> if(maximumResponse==null)input.readBytes() else {val out=java.io.ByteArrayOutputStream();val buffer=ByteArray(16384);while(true){val count=input.read(buffer);if(count<0)break;if(out.size().toLong()+count>maximumResponse)throw ApiFailure(502,"The server response exceeds the allowed file or chunk size.");out.write(buffer,0,count)};out.toByteArray()} }
        } catch (failure: ApiFailure) { throw failure }
        catch (failure: java.net.SocketTimeoutException) { throw ApiFailure(0, "The server took too long to respond. Retry this same save before creating another transaction.") }
        catch (failure: java.io.IOException) { throw ApiFailure(0, "Cannot reach Apex Books. Check your connection. Retry the same save to recover an interrupted response.") }
        finally { connection.disconnect() }
      }
    }

    suspend fun records(companyId: String): List<JSONObject> = withContext(Dispatchers.Default) {
        val rows = mutableListOf<JSONObject>(); var offset = 0
        while (true) {
            val page = (request(company(companyId, "/records?compact=true&limit=500&offset=$offset")) as JSONArray).objects()
            rows.addAll(page); if (page.size < 500) break; offset += 500
        }
        rows
    }
    suspend fun cancelRecord(companyId: String, id: String, reason: String): JSONObject =
        request(company(companyId, "/records/${encode(id)}/cancel"), "POST", JSONObject().put("reason", reason)) as JSONObject
    /** Posts an invoice or bill and its first receipt/payout atomically; the retry key covers both. */
    suspend fun saveRecordWithPayment(companyId: String, document: JSONObject, payment: JSONObject, retryKey: String): JSONObject =
        request(company(companyId, "/records/with-payment"), "POST", JSONObject().put("document", document).put("payment", payment), retryKey) as JSONObject
    suspend fun record(companyId: String, id: String): JSONObject = request(company(companyId, "/records/${encode(id)}")) as JSONObject
    suspend fun saveRecord(companyId: String, body: JSONObject, retryKey: String, previous: JSONObject? = null): JSONObject {
        val suffix = if (previous == null) "/records" else if (body.s("kind") in setOf("estimate", "proforma", "sales_order", "purchase_order")) "/drafts/${previous.s("id")}" else "/documents/${previous.s("id")}"
        return request(company(companyId, suffix), if (previous == null) "POST" else "PUT", body, retryKey) as JSONObject
    }
}
