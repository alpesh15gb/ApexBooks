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
    private fun scrollTo(device:UiDevice,text:String) {
        repeat(10){if(device.hasObject(By.text(text)))return;device.swipe(device.displayWidth/2,device.displayHeight*3/4,device.displayWidth/2,device.displayHeight/4,30);device.waitForIdle()}
        assertTrue("Visible action: $text",device.hasObject(By.text(text)))
    }

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
            val party=api.saveRecord(company.s("id"),JSONObject().put("kind","party").put("name","UI Smoke Buyer").put("data",JSONObject().put("party_type","both").put("payment_terms_days",30)),UUID.randomUUID().toString())
            val item=api.saveRecord(company.s("id"),JSONObject().put("kind","item").put("name","UI Reorder Item").put("data",JSONObject().put("item_type","goods").put("track_stock",true).put("unit","pcs").put("sale_rate","100").put("purchase_rate","40").put("gst_rate","0").put("tax_treatment","nil_rated").put("low_stock_threshold","3")),UUID.randomUUID().toString())
            api.saveRecord(company.s("id"),JSONObject().put("kind","purchase_bill").put("name","UI Smoke Buyer").put("date",today()).put("data",JSONObject().put("party_id",party.s("id")).put("supplier_state","27").put("place_of_supply","27").put("lines",JSONArray().put(JSONObject().put("item_id",item.s("id")).put("description","UI Reorder Item").put("quantity","1").put("rate","40").put("gst_rate","0").put("tax_treatment","nil_rated")))),UUID.randomUUID().toString())
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
        // The remaining journeys are review-only: no order or second invoice is posted.
        device.pressBack()
        assertTrue(device.wait(Until.hasObject(By.text("Home")),15000));device.findObject(By.text("Home")).click()
        scrollTo(device,"Low stock & reorder review");device.findObject(By.text("Low stock & reorder review")).click()
        assertTrue(device.wait(Until.hasObject(By.text("UI Reorder Item")),30000))
        scrollTo(device,"Review purchase order · 1 items");device.findObject(By.text("Review purchase order · 1 items")).click()
        assertTrue(device.wait(Until.hasObject(By.text("New Purchase Order")),15000))
        device.findObject(By.text("Enter manually")).click()
        assertTrue(device.wait(Until.hasObject(By.text("UI Smoke Buyer")),15000));device.findObject(By.text("UI Smoke Buyer")).click()
        device.findObject(By.text("Next: add items")).click()
        assertTrue(device.wait(Until.hasObject(By.text("UI Reorder Item")),15000));device.findObject(By.text("UI Reorder Item")).click()
        scrollTo(device,"Check this party’s item prices");device.findObject(By.text("Check this party’s item prices")).click()
        assertTrue(device.wait(Until.hasObject(By.text("Last posted price for this exact party and item.")),30000))
        scrollTo(device,"Apply suggested price & tax basis");device.findObject(By.text("Apply suggested price & tax basis")).click()
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-reorder-price-review.png"))
        device.findObject(By.desc("Close entry")).click()
        assertTrue(device.wait(Until.hasObject(By.text("Discard draft")),15000));device.findObject(By.text("Discard draft")).click()
        scrollTo(device,"New invoice");device.findObject(By.text("New invoice")).click()
        assertTrue(device.wait(Until.hasObject(By.text("New Sales Invoice")),15000))
        device.findObject(By.text("Enter manually")).click()
        assertTrue(device.wait(Until.hasObject(By.text("UI Smoke Buyer")),15000));device.findObject(By.text("UI Smoke Buyer")).click()
        scrollTo(device,"Check party payment terms");device.findObject(By.text("Check party payment terms")).click()
        assertTrue(device.wait(Until.hasObject(By.text("Use suggested due date")),30000));device.findObject(By.text("Use suggested due date")).click()
        assertTrue("Explicit terms Apply sets the suggested date",device.hasObject(By.text(java.time.LocalDate.parse(today()).plusDays(30).toString())))
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-party-terms-review.png"))
        device.findObject(By.desc("Close entry")).click()
        assertTrue(device.wait(Until.hasObject(By.text("Discard draft")),15000));device.findObject(By.text("Discard draft")).click()
        val afterReview=api.records(companyIds.getValue(target))
        assertEquals("Reviewing suggestions creates no purchase order",0,afterReview.count{it.s("kind")=="purchase_order"})
        assertEquals("Discarded terms review creates no new invoice",1,afterReview.count{it.s("kind")=="sales_invoice"})
        api.logout()
    }
}
