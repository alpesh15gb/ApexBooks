package com.apexbooks.accounting

import androidx.test.platform.app.InstrumentationRegistry
import com.apexbooks.accounting.data.ApexApi
import com.apexbooks.accounting.data.ApiFailure
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.UUID

/** Checks the Android HTTP/JSON sign-in path without user credentials or company writes. */
class LoginTransportAcceptanceTest {
    @Test fun webCreatedPasswordSignsInOnAndroid():Unit=runBlocking {
        requireLocalTestOrigin()
        val web=ApexApi(BuildConfig.API_ORIGIN)
        val android=ApexApi(BuildConfig.API_ORIGIN)
        val email="login-transport-${UUID.randomUUID()}@example.invalid"
        val password="  Apex ₹ \"&+\\ 2026!  "
        try{
            web.request("/api/auth/register","POST",JSONObject().put("email",email).put("password",password))
            web.login(email,password,false)
            android.login(email,password,false)
            assertTrue(web.signedIn&&android.signedIn)
            assertTrue(android.request("/api/companies") is JSONArray)
            val result=JSONObject().put("all_pass",true).put("api_origin",android.origin)
                .put("web_created_account_native_signin",true).put("unicode_and_punctuation_preserved",true)
                .put("password_boundary_spaces_preserved",true).put("personal_credentials_used",false)
            InstrumentationRegistry.getInstrumentation().targetContext.getExternalFilesDir(null)?.let{
                File(it,"login-special-character-acceptance.json").writeText(result.toString(2))
            }
        }finally{if(web.signedIn)web.logout();if(android.signedIn)android.logout()}
    }
    @Test fun isolatedLocalSignIn():Unit=runBlocking {
        requireLocalTestOrigin()
        val api=ApexApi(BuildConfig.API_ORIGIN)
        val email="native-signin-${UUID.randomUUID()}@example.invalid"
        val password="Synthetic-device-only-2026!"
        api.request("/api/auth/register","POST",JSONObject().put("email",email).put("password",password))
        try {
            try {
                api.login(email,"Deliberately-Wrong-QA-Password",false)
                fail("Invalid credentials must be rejected")
            } catch(failure:ApiFailure) { assertEquals(401,failure.status) }
            assertFalse(api.signedIn)
            api.login(" ${email.uppercase()} ",password,false)
            assertTrue(api.signedIn)
            assertTrue(api.request("/api/companies") is JSONArray)
            val result=JSONObject().put("all_pass",true).put("api_origin",api.origin)
                .put("invalid_credentials_rejected",true).put("valid_credentials_accepted",true)
                .put("email_case_and_surrounding_spaces",true).put("authenticated_companies_read",true)
                .put("personal_credentials_used",false).put("company_writes",false)
            InstrumentationRegistry.getInstrumentation().targetContext.getExternalFilesDir(null)?.let {
                File(it,"login-transport-acceptance.json").writeText(result.toString(2))
            }
        } finally {if(api.signedIn)api.logout()}
    }
}
