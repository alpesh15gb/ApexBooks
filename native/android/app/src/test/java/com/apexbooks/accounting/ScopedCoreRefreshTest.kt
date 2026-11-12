package com.apexbooks.accounting
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
class ScopedCoreRefreshTest {
 class Failure(val status:Int):Exception("Synthetic failure")
 @Test fun inspectBothFailuresAndSuppressStaleResults()=runBlocking {
  for(mode in listOf("mixed","transient","stale","success")){
   var current=true;var invalid=false;var published=false
   val a=CompletableDeferred<Int>();val b=CompletableDeferred<Int>();var error:Throwable?=null
   val work=launch(start=CoroutineStart.UNDISPATCHED){try{scopedCoreRefresh({a.await()},{b.await()},{current},{it is Failure&&it.status in setOf(403,404)},{invalid=true},{_,_->published=true})}catch(e:Exception){error=e}}
   yield();if(mode=="stale")current=false
   if(mode=="success"){a.complete(1);b.complete(2)}else{a.completeExceptionally(Failure(503));b.completeExceptionally(Failure(if(mode=="transient")503 else 404))}
   work.join();assertEquals(mode=="mixed",invalid);assertEquals(mode=="success",published);assertEquals(mode in listOf("mixed","transient"),error!=null)
  }
 }
 @Test fun coroutineCancellationDoesNotPublishOrInvalidate()=runBlocking {
  var invalid=false;var published=false
  val work=launch{scopedCoreRefresh({awaitCancellation()},{1},{true},{true},{invalid=true},{_,_->published=true})}
  yield();work.cancelAndJoin();assertFalse(invalid);assertFalse(published)
 }
}
