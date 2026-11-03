package com.apexbooks.accounting

/** Load completion is not a server snapshot time or a cross-client consistency guarantee. */
data class HistorySnapshot(val loadedAt:java.time.Instant?=null,val refreshFailed:Boolean=false) {
    fun completed(at:java.time.Instant,current:Boolean)=if(current)HistorySnapshot(at)else this
    fun failed(current:Boolean)=if(current)copy(refreshFailed=true)else this
    fun label():String {
        val time=loadedAt?.let{java.time.format.DateTimeFormatter.ofPattern("d MMM yyyy HH:mm:ss 'IST'").withZone(java.time.ZoneId.of("Asia/Kolkata")).format(it)}
        return if(time==null)"Company history is not loaded. Refresh to try again."
        else (if(refreshFailed)"Refresh failed. Showing prior history loaded $time." else "History loaded $time.")+" This is a saved view, not live data. Refresh for changes from other devices."
    }
}
