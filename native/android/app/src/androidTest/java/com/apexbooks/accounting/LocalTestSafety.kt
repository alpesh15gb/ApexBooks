package com.apexbooks.accounting

/** Instrumentation may create data only in an explicitly local debug backend. */
fun requireLocalTestOrigin() {
    val uri=java.net.URI(BuildConfig.API_ORIGIN)
    require(BuildConfig.DEBUG && uri.scheme=="http" && uri.host in setOf("10.0.2.2","127.0.0.1","localhost","::1")) {
        "Instrumentation is local-only. Use a debug build with an isolated local API; production/hosted writes are forbidden."
    }
}
