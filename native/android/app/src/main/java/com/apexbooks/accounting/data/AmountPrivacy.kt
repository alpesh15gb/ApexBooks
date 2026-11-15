package com.apexbooks.accounting.data

import android.content.Context

/**
 * Dashboard amounts can be hidden on this device. Hiding needs no password; showing them again needs the
 * account password, which the server verifies. Everything here that is not storage is pure so it can be unit tested.
 */
object AmountPrivacy {
    const val MASK = "₹ ••••••"

    fun text(hidden: Boolean, formatted: String): String = if (hidden) MASK else formatted

    /** A server without the password check cannot reveal by password, so it must not strand the user behind masked figures. */
    fun revealUnsupported(error: Exception): Boolean = error is ApiFailure && error.status in setOf(404, 405)

    fun revealError(error: Exception): String = when {
        error is ApiFailure && error.status == 429 -> "Too many attempts. Wait a few minutes and try again."
        error is ApiFailure && error.status == 403 -> "That password is not correct."
        else -> error.message ?: "Could not check your password. Try again."
    }
}

/** The choice is remembered on this device only; if storage fails, amounts are never hidden by accident. */
class AmountPrivacyPreference(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences("apex_display", Context.MODE_PRIVATE)
    var hidden: Boolean
        get() = runCatching { preferences.getBoolean(KEY, false) }.getOrDefault(false)
        set(value) { runCatching { preferences.edit().putBoolean(KEY, value).apply() } }

    private companion object { const val KEY = "dashboard_amounts_hidden" }
}
