package com.apexbooks.accounting

import com.apexbooks.accounting.data.RetrySubmission

/** A rejection of a replay attempt cannot establish the outcome of the earlier edit. */
fun recordEditWriteFailed(submission:RetrySubmission,error:Exception,recordEdit:Boolean,wasUnknown:Boolean,definitiveConflict:Boolean=false){
    if(recordEdit&&wasUnknown)return
    submission.failed(error,definitiveConflict)
}
