package com.apexbooks.accounting

import com.apexbooks.accounting.data.ApiFailure
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class RecurringToolsTest {
    @Test fun defaultStartUsesIndiaBusinessMidnightNotDeviceTimezone(){
        assertEquals("2026-11-02",recurringBusinessDate(java.time.Instant.parse("2026-11-02T18:29:59Z")))
        assertEquals("2026-11-03",recurringBusinessDate(java.time.Instant.parse("2026-11-02T18:30:00Z")))
    }

    @Test fun scheduleValidationDoesNotInventOccurrenceDates(){
        assertNull(recurringScheduleIssue("Month end","2026-01-31","monthly","1","2026-03-31"))
        assertNull(recurringScheduleIssue("Weekly","2026-02-28","weekly","12",""))
        for(interval in listOf("0","13","1.5","bad"))assertNotNull(recurringScheduleIssue("Name","2026-01-01","monthly",interval,""))
        assertNotNull(recurringScheduleIssue("Name","2026-02-30","monthly","1",""))
        assertNotNull(recurringScheduleIssue("Name","2026-02-01","weekly","1","2026-01-31"))
        assertNotNull(recurringScheduleIssue("Name","2026-01-01","daily","1",""))
    }
    @Test fun unknownRequestRetainsExactOccurrenceAndKey(){
        val command=RecurringCommand();val key=command.key
        command.body(JSONObject().put("occurrence_date","2026-01-31"));command.failed(ApiFailure(503,"unknown"))
        assertTrue(command.unresolved);assertEquals(key,command.key)
        assertEquals("2026-01-31",command.body(JSONObject().put("occurrence_date","2026-02-28")).getString("occurrence_date"))
        command.succeeded();assertFalse(command.unresolved)
    }
    @Test fun recurringDefinitiveConflictCanReloadAndCorrect(){
        val command=RecurringCommand();val key=command.key
        command.body(JSONObject().put("version",0));command.failed(ApiFailure(409,"Template changed; reload"))
        assertFalse(command.unresolved);assertNotEquals(key,command.key)
        assertEquals(1,command.body(JSONObject().put("version",1)).getInt("version"))
    }
    @Test fun validationFailureDoesNotLockUnsavedTemplate(){
        val command=RecurringCommand();command.body(JSONObject().put("interval",13));command.failed(ApiFailure(422,"invalid"))
        assertFalse(command.unresolved);assertEquals(1,command.body(JSONObject().put("interval",1)).getInt("interval"))
    }
}
