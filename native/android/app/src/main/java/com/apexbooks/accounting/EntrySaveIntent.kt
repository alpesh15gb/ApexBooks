package com.apexbooks.accounting

/** Preserve the original post-success navigation while a write outcome is uncertain. */
class EntrySaveIntent {
    private var pending:Boolean?=null
    fun forAttempt(keepOpen:Boolean,unresolved:Boolean):Boolean {
        if(!unresolved||pending==null)pending=keepOpen
        return pending!!
    }
    fun failed(unresolved:Boolean){if(!unresolved)pending=null}
    fun succeeded(){pending=null}
}
