package com.apexbooks.accounting

import android.content.Intent
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.UUID

class LocalUiAcceptanceTest {
    @Test fun signInAndSwitchSyntheticCompanies():Unit=runBlocking {
        requireLocalTestOrigin()
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val context=instrumentation.targetContext
        val api=ApexApi(BuildConfig.API_ORIGIN)
        val email="native-ui-${UUID.randomUUID()}@example.invalid"
        val password="Synthetic-device-only-2026!"
        api.request("/api/auth/register","POST",JSONObject().put("email",email).put("password",password))
        api.login(email,password,false)
        val companyIds=mutableMapOf<String,String>()
        for(name in listOf("UI Local Alpha","UI Local Beta")){
            val company=api.request("/api/companies","POST",JSONObject().put("name",name).put("tax_mode","unregistered").put("state_code","27")) as JSONObject
            companyIds[name]=company.s("id")
            api.saveRecord(company.s("id"),JSONObject().put("kind","sales_invoice").put("name","UI Smoke Buyer").put("date",today()).put("data",JSONObject().put("place_of_supply","27").put("lines",JSONArray().put(JSONObject().put("description","UI test service").put("quantity","1").put("rate","100").put("gst_rate","0")))),UUID.randomUUID().toString())
        }
        api.logout()
        val launch=context.packageManager.getLaunchIntentForPackage(context.packageName)!!.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        instrumentation.startActivitySync(launch)
        val device=UiDevice.getInstance(instrumentation)
        assertTrue("Sign-in screen appears",device.wait(Until.hasObject(By.text("Sign in")),60000))
        val fields=device.findObjects(By.clazz("android.widget.EditText"))
        assertEquals("Email and password fields",2,fields.size)
        fields[0].click();fields[0].text=email;fields[1].click();fields[1].text=password
        device.pressBack()
        device.findObject(By.text("Sign in")).click()
        assertTrue("Native dashboard opens",device.wait(Until.hasObject(By.text("Your business")),60000))
        assertTrue("Synthetic company visible",device.wait(Until.hasObject(By.text("UI Local Alpha")),30000)||device.hasObject(By.text("UI Local Beta")))
        val target=if(device.hasObject(By.text("UI Local Alpha")))"UI Local Beta"else"UI Local Alpha"
        device.findObject(By.desc("Switch company")).click()
        assertTrue("Company selector lists other company",device.wait(Until.hasObject(By.text(target)),15000))
        device.findObject(By.text(target)).click()
        assertTrue("Company selector closes",device.wait(Until.gone(By.text("Each company keeps its own books and settings.")),15000))
        assertTrue("Second workspace opens",device.wait(Until.hasObject(By.text(target)),30000))
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-dashboard.png"))
        device.findObject(By.text("Transactions")).click()
        assertTrue("Invoice is searchable in native register",device.wait(Until.hasObject(By.text("UI Smoke Buyer")),30000))
        device.findObject(By.text("UI Smoke Buyer")).click()
        assertTrue("Contextual collection action appears",device.wait(Until.hasObject(By.text("Record payment received")),30000))
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-transaction-detail.png"))
        device.findObject(By.text("Record payment received")).click()
        assertTrue("Prefilled receipt editor opens",device.wait(Until.hasObject(By.text("Save receipt")),30000))
        device.findObject(By.text("Save receipt")).click()
        assertTrue("Successful save closes editor",device.wait(Until.gone(By.text("Save receipt")),30000))
        api.login(email,password,false)
        val records=api.records(companyIds.getValue(target))
        assertEquals("Invoice balance settled by native UI",0,records.first{it.s("kind")=="sales_invoice"}.decimal("outstanding").signum())
        assertEquals("Exactly one payment posted",1,records.count{it.s("kind")=="payment_in"})
        api.logout()
    }
}
