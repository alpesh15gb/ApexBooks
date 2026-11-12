package com.apexbooks.accounting
import org.junit.Assert.*
import org.junit.Test
class EntrySaveIntentTest {
 @Test fun uncertainSaveAndNewRetryKeepsOriginalIntent(){val intent=EntrySaveIntent();assertTrue(intent.forAttempt(true,false));intent.failed(true);assertTrue(intent.forAttempt(false,true));intent.succeeded();assertFalse(intent.forAttempt(false,false))}
 @Test fun uncertainOrdinarySaveCannotBecomeSaveAndNew(){val intent=EntrySaveIntent();assertFalse(intent.forAttempt(false,false));intent.failed(true);assertFalse(intent.forAttempt(true,true))}
 @Test fun definitiveRejectionAllowsANewChoice(){val intent=EntrySaveIntent();assertTrue(intent.forAttempt(true,false));intent.failed(false);assertFalse(intent.forAttempt(false,false))}
 @Test fun repeatedLostResponsesDoNotChangeIntent(){val intent=EntrySaveIntent();assertTrue(intent.forAttempt(true,false));repeat(3){intent.failed(true);assertTrue(intent.forAttempt(false,true))};intent.succeeded()}
}
