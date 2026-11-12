"""Compile actual Android session/request/transfer methods against in-memory URL connections."""
from pathlib import Path
import argparse,sys,tempfile
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'native/tests'))
from kotlin_toolchain import add_arguments,run_proof
p=argparse.ArgumentParser();add_arguments(p);args=p.parse_args()
s=(root/'native/android/app/src/main/java/com/apexbooks/accounting/data/ApexApi.kt').read_text()
methods=s[s.index('class ApexApi('):s.index('    suspend fun records(')]+'}\n'
fixture=r'''
import kotlinx.coroutines.*
import java.net.*
import java.io.*
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
class JSONObject(text:String="") {private val values=mutableMapOf<String,String>();init{if(text.contains("private")&&transport.parseDelay)transport.hold();Regex("\"([^\"]+)\":\"([^\"]*)\"").findAll(text).forEach{values[it.groupValues[1]]=it.groupValues[2]}};fun put(k:String,v:Any)=apply{values[k]=v.toString()};fun opt(k:String):Any?=values[k];override fun toString()=values.entries.joinToString(",","{","}"){"\"${it.key}\":\"${it.value}\""}}
class JSONArray(text:String=""){fun objects()=emptyList<JSONObject>()}
fun JSONObject.s(key:String)=opt(key)?.toString()?:""
fun encode(value:String)=URLEncoder.encode(value,"UTF-8")
class SessionVault {fun load(origin:String):JSONObject?=null;fun clear(origin:String){};fun save(origin:String,value:JSONObject){}}
class ApiFailure(val status:Int,message:String):Exception(message)
METHODS
class Transport(val bodyDelay:Boolean,val repeatToken:Boolean=false,val status:Int=200,val parseDelay:Boolean=false) {
 val entered=CountDownLatch(1);val release=CountDownLatch(1);var logins=0;var calls=0
 fun hold(){entered.countDown();check(release.await(5,TimeUnit.SECONDS)){"test response timed out"}}
 fun connection(url:URL)=object:HttpURLConnection(url){
  val login=url.path=="/api/auth/login"
  override fun connect(){};override fun disconnect(){};override fun usingProxy()=false
  override fun getOutputStream():OutputStream=ByteArrayOutputStream()
  override fun getResponseCode():Int{if(!login){calls++;if(!bodyDelay&&!parseDelay)hold()};return if(login)200 else status}
  override fun getErrorStream():InputStream=ByteArrayInputStream("{\"detail\":\"Synthetic denied\"}".toByteArray())
  override fun getInputStream():InputStream{val text=if(login)"{\"token\":\"test-${if(repeatToken)1 else ++logins}\"}" else "{\"value\":\"private\"}";return object:ByteArrayInputStream(text.toByteArray()){override fun read(bytes:ByteArray,offset:Int,length:Int):Int{if(!login&&bodyDelay)hold();return super.read(bytes,offset,length)}}}
 }
}
lateinit var transport:Transport
fun main()=runBlocking {
 URL.setURLStreamHandlerFactory{scheme->if(scheme=="https")object:URLStreamHandler(){override fun openConnection(url:URL)=transport.connection(url)}else null}
 for(route in listOf("request","bytes","raw","upload"))for(delay in listOf("headers","body","parse"))for(change in listOf("same","logout","replacement","same-token")){
  if(delay=="parse"&&route !in listOf("request","upload"))continue
  transport=Transport(delay=="body",change=="same-token",parseDelay=delay=="parse");val api=ApexApi("https://synthetic.invalid");api.login("first@example.invalid","synthetic",false)
  val pending=async(Dispatchers.Default){runCatching{when(route){"request"->api.request("/api/held","POST",JSONObject().put("amount","100"),"original-key");"bytes"->api.bytes("/api/held");"raw"->api.rawBytes("/api/held");else->api.upload("/api/held","POST",byteArrayOf(1),"application/octet-stream","original-key")}}}
  check(withContext(Dispatchers.IO){transport.entered.await(5,TimeUnit.SECONDS)})
  if(change=="logout")api.forget();if(change=="replacement"||change=="same-token")api.login("second@example.invalid","synthetic",false)
  transport.release.countDown();val result=pending.await()
  if(change=="same")check(result.isSuccess){"Current request failed: $result"}else check((result.exceptionOrNull() as? ApiFailure)?.status==0){"Stale successful $route response escaped after $change at $delay: $result"}
  check(api.signedIn==(change!="logout"));check(transport.calls==1)
 }
 for(operation in listOf("logout","401","challenge"))for(replace in listOf(false,true)){
  transport=Transport(false,true,if(operation=="logout")200 else 401);val api=ApexApi("https://synthetic.invalid");api.login("first@example.invalid","synthetic",false)
  val pending=async(Dispatchers.Default){runCatching{if(operation=="logout")api.logout() else api.request(if(operation=="challenge")"/api/auth/change-password" else "/api/held")}}
  check(withContext(Dispatchers.IO){transport.entered.await(5,TimeUnit.SECONDS)});if(replace)api.login("second@example.invalid","synthetic",false)
  transport.release.countDown();val result=pending.await()
  check(api.signedIn==(replace||operation=="challenge")){"$operation changed replacement/current session incorrectly"}
  if(replace)check(api.email=="second@example.invalid")
  if(operation!="logout")check((result.exceptionOrNull() as? ApiFailure)?.status==401)
  else if(replace)check((result.exceptionOrNull() as? ApiFailure)?.status==0)else check(result.isSuccess)
 }
 println("PASS Android current/old logout,401 and credential challenge: 6 cases")
 println("PASS actual Android request/bytes/raw/upload session ownership: 40 delayed-header/body/parse cases")
}
'''.replace('METHODS',methods)
with tempfile.TemporaryDirectory(prefix='apex-android-response-') as temp:
 temp=Path(temp);(temp/'Proof.kt').write_text(fixture);(temp/'BuildConfig.kt').write_text('package com.apexbooks.accounting\nobject BuildConfig {const val DEBUG=true;const val VERSION_NAME="synthetic"}')
 run_proof(args,[temp/'Proof.kt',temp/'BuildConfig.kt'],temp)
