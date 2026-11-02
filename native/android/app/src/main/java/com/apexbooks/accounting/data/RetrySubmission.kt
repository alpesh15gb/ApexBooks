package com.apexbooks.accounting.data

import org.json.JSONObject

/** Keeps an uncertain financial write byte-for-byte stable until its outcome is known. */
class RetrySubmission {
    private var pending: String? = null
    val unresolved: Boolean get() = pending != null
    fun body(candidate: JSONObject): JSONObject {
        if (pending == null) pending = candidate.toString()
        return JSONObject(pending!!)
    }
    fun succeeded() { pending = null }
    fun failed(error: Exception) {
        // A timeout, server error, or in-progress conflict may follow a committed write.
        if (error is ApiFailure && error.status in 400..499 && error.status !in setOf(408, 409)) pending = null
    }
}
