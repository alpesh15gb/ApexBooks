package com.apexbooks.accounting

import org.junit.Assert.*
import org.junit.Test

class PlanningToolsTest {
    @Test fun creditLimitIsOptionalWarningConfigurationWithMeaningfulCurrencyPrecision(){
        for(value in listOf("","0","100.00","1.2300","9999999999999.99"))assertNull(masterPlanningIssue("party","","",value))
        for(value in listOf("-1","1.001","10000000000000","abc"))assertNotNull(masterPlanningIssue("party","","",value))
    }

    @Test fun optionalPaymentTermsAllowBoundedWholeDaysOnly(){
        for(value in listOf("","0","30","3650"))assertNull(masterPlanningIssue("party",value,""))
        for(value in listOf("-1","3651","1.5","abc"))assertNotNull(masterPlanningIssue("party",value,""))
    }
    @Test fun reorderThresholdIsOptionalNonnegativePreciseQuantity(){
        for(value in listOf("","0","0.001","1.0000","0.1230","999999999999.999"))assertNull(masterPlanningIssue("item","",value))
        for(value in listOf("-1","0.0001","1000000000000","abc"))assertNotNull(masterPlanningIssue("item","",value))
    }
}
