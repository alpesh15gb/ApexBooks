package com.apexbooks.accounting
import kotlinx.coroutines.*
suspend fun <A,B> scopedCoreRefresh(first:suspend()->A,second:suspend()->B,current:()->Boolean,denied:(Throwable)->Boolean,invalidate:()->Unit,publish:(A,B)->Unit)=supervisorScope {
    suspend fun <T> capture(load:suspend()->T):Result<T> = try{Result.success(load())}catch(e:CancellationException){throw e}catch(e:Exception){Result.failure(e)}
    val a=async{capture(first)};val b=async{capture(second)}
    val left=a.await();val right=b.await()
    if(!current())return@supervisorScope
    val failures=listOfNotNull(left.exceptionOrNull(),right.exceptionOrNull())
    if(failures.isNotEmpty()){
        if(failures.any(denied))invalidate()
        throw failures.first()
    }
    publish(left.getOrThrow(),right.getOrThrow())
}
