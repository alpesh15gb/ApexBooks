package com.apexbooks.accounting
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
class ScopedExternalActionTest {
 @Test fun delayedBrandingNeverLaunchesAcrossStaleContext()=runBlocking {
  for(scenario in listOf("current","stale-success","stale-failure","current-failure","stale-final")){
   val pending=CompletableDeferred<String>();var current=true;val launched=mutableListOf<String>()
   val job=launch(start=CoroutineStart.UNDISPATCHED){scopedExternalAction({pending.await()},{current},{value->if(scenario=="stale-final")current=false;"captured-company:$value"},{launched.add(it)})}
   if(scenario.startsWith("stale-"))current=scenario=="stale-final"
   if(scenario.endsWith("failure"))pending.completeExceptionally(Exception("Synthetic branding error"))else pending.complete("synthetic-upi")
   job.join();assertEquals(if(scenario.startsWith("current"))1 else 0,launched.size)
   if(launched.isNotEmpty())assertEquals(if(scenario=="current")"captured-company:synthetic-upi" else "captured-company:",launched.single())
  }
 }
 @Test fun cancellationDoesNotFallBackToExternalLaunch()=runBlocking {
  var launched=false
  try{scopedExternalAction({throw CancellationException()},{true},{it},{launched=true});fail("Cancellation expected")}catch(_:CancellationException){}
  assertFalse(launched)
 }
}
