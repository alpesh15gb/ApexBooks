package com.apexbooks.accounting

import android.content.Intent
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import org.junit.Rule
import org.junit.rules.TestWatcher
import org.junit.runner.Description
import java.io.File
import java.util.UUID

class LocalUiAcceptanceTest {
    @get:Rule val failureEvidence=object:TestWatcher(){
        override fun failed(error:Throwable,description:Description){
            val instrumentation=InstrumentationRegistry.getInstrumentation()
            val device=UiDevice.getInstance(instrumentation)
            val directory=instrumentation.targetContext.getExternalFilesDir(null)?:return
            // Dedicated synthetic emulator only; capture the actual failing UI before another test resets it.
            runCatching{device.takeScreenshot(File(directory,"local-native-failure.png"))}
            runCatching{device.dumpWindowHierarchy(File(directory,"local-native-failure.xml"))}
        }
    }

    private fun scrollTo(device:UiDevice,text:String)=scrollTo(device,By.text(text),text)
    private fun scrollTo(device:UiDevice,selector:BySelector,label:String) {
        if(device.wait(Until.hasObject(selector),2000))return
        repeat(8){if(device.hasObject(selector))return;device.swipe(device.displayWidth/2,device.displayHeight*3/4,device.displayWidth/2,device.displayHeight/4,30);device.waitForIdle()}
        // A previous action can leave the same form scrolled below its next control.
        repeat(16){if(device.hasObject(selector))return;device.swipe(device.displayWidth/2,device.displayHeight/4,device.displayWidth/2,device.displayHeight*3/4,30);device.waitForIdle()}
        assertTrue("Visible action: $label",device.hasObject(selector))
    }
    private fun chooseSavedParty(device:UiDevice){
        val selector=By.desc("Saved party · Enter manually")
        scrollTo(device,selector,"Saved party selector")
        assertTrue("Saved party is an accessible clickable control",device.findObject(selector).isClickable)
        device.findObject(selector).click()
        assertTrue(device.wait(Until.hasObject(By.text("UI Smoke Buyer")),15000));device.findObject(By.text("UI Smoke Buyer")).click()
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
        for((_,cid) in companyIds){
            val report=api.request(api.company(cid,"/reports/reorder?as_of=${today()}")) as JSONObject
            assertEquals("Synthetic fixture has one low-stock item",1,report.a("rows").length())
            assertEquals("UI Reorder Item",report.a("rows").getJSONObject(0).s("name"))
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
        assertTrue("Reorder report loaded",device.wait(Until.hasObject(By.textContains("items at or below threshold")),30000))
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-reorder-open.png"))
        scrollTo(device,"UI Reorder Item")
        assertTrue("Exact seeded low-stock item is visible after scrolling",device.hasObject(By.text("UI Reorder Item")))
        scrollTo(device,"Review purchase order · 1 items");device.findObject(By.text("Review purchase order · 1 items")).click()
        assertTrue(device.wait(Until.hasObject(By.text("New Purchase Order")),15000))
        chooseSavedParty(device)
        device.findObject(By.text("Next: add items")).click()
        assertTrue("Reorder draft preserves the selected item",device.wait(Until.hasObject(By.desc("Item / service · UI Reorder Item")),15000))
        scrollTo(device,"Check this party’s item prices");device.findObject(By.text("Check this party’s item prices")).click()
        scrollTo(device,"Last posted price for this exact party and item.");assertTrue(device.hasObject(By.text("Last posted price for this exact party and item.")))
        scrollTo(device,"Apply suggested price & tax basis");device.findObject(By.text("Apply suggested price & tax basis")).click()
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-reorder-price-review.png"))
        device.findObject(By.desc("Close entry")).click()
        assertTrue(device.wait(Until.hasObject(By.text("Discard draft")),15000));device.findObject(By.text("Discard draft")).click()
        scrollTo(device,"New invoice");device.findObject(By.text("New invoice")).click()
        assertTrue(device.wait(Until.hasObject(By.text("New Sales Invoice")),15000))
        chooseSavedParty(device)
        scrollTo(device,"Check party payment terms");device.findObject(By.text("Check party payment terms")).click()
        scrollTo(device,"Use suggested due date");assertTrue(device.hasObject(By.text("Use suggested due date")));device.findObject(By.text("Use suggested due date")).click()
        scrollTo(device,By.desc("Due date · optional · "+java.time.LocalDate.parse(today()).plusDays(30).toString()),"Applied due date")
        assertTrue("Explicit terms Apply sets the suggested date",device.hasObject(By.desc("Due date · optional · "+java.time.LocalDate.parse(today()).plusDays(30).toString())))
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-party-terms-review.png"))
        device.findObject(By.desc("Close entry")).click()
        assertTrue(device.wait(Until.hasObject(By.text("Keep editing")),15000));device.findObject(By.text("Keep editing")).click()
        assertTrue("Keep editing retains the invoice editor",device.hasObject(By.text("New Sales Invoice")))
        device.findObject(By.desc("Close entry")).click()
        assertTrue(device.wait(Until.hasObject(By.text("Discard draft")),15000));device.findObject(By.text("Discard draft")).click()
        val afterReview=api.records(companyIds.getValue(target))
        assertEquals("Reviewing suggestions creates no purchase order",0,afterReview.count{it.s("kind")=="purchase_order"})
        assertEquals("Discarded terms review creates no new invoice",1,afterReview.count{it.s("kind")=="sales_invoice"})
        // Create a real second invoice entirely through the native document editor.
        scrollTo(device,"New invoice");device.findObject(By.text("New invoice")).click()
        assertTrue(device.wait(Until.hasObject(By.text("New Sales Invoice")),15000))
        chooseSavedParty(device)
        device.findObject(By.text("Next: add items")).click()
        val itemSelector=By.desc("Item / service · Enter a description");scrollTo(device,itemSelector,"Item / service selector");device.findObject(itemSelector).click()
        assertTrue(device.wait(Until.hasObject(By.text("UI Reorder Item")),15000));device.findObject(By.text("UI Reorder Item")).click()
        device.findObject(By.text("Review document")).click()
        assertTrue("API preview enables native save",device.wait(Until.hasObject(By.text("Save invoice").enabled(true)),30000))
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-invoice-review.png"))
        device.findObject(By.text("Save invoice")).click()
        assertTrue("Native invoice save closes editor",device.wait(Until.gone(By.text("New Sales Invoice")),30000))
        val saved=api.records(companyIds.getValue(target));val priorIds=afterReview.map{it.s("id")}.toSet()
        val created=saved.single{it.s("kind")=="sales_invoice"&&it.s("id") !in priorIds}
        assertTrue("Native-created invoice posted",created.optBoolean("posted"))
        assertEquals("Native-created invoice amount",0,created.decimal("amount").compareTo(java.math.BigDecimal("100")))
        assertEquals("Native-created invoice remains unpaid",0,created.decimal("outstanding").compareTo(java.math.BigDecimal("100")))
        assertEquals("Invoice save does not duplicate collection",1,saved.count{it.s("kind")=="payment_in"})
        // Actual receipt controls + system picker. No API-upload shortcut is used.
        val receiptName="apex-ui-receipt-${UUID.randomUUID()}.pdf"
        val receiptPath="/sdcard/Download/$receiptName"
        val receiptBytes="%PDF-1.4\n% Synthetic Android UI receipt\n%%EOF\n".toByteArray()
        val encoded=android.util.Base64.encodeToString(receiptBytes,android.util.Base64.NO_WRAP)
        device.executeShellCommand("mkdir -p /sdcard/Download; printf '%s' '$encoded' | base64 -d > '$receiptPath'")
        try {
            device.findObject(By.text("More")).click();scrollTo(device,"Purchase bills");device.findObject(By.text("Purchase bills")).click()
            assertTrue(device.wait(Until.hasObject(By.text("UI Smoke Buyer")),30000));device.findObject(By.text("UI Smoke Buyer")).click()
            scrollTo(device,"Retained receipts & attachments");device.findObject(By.text("Retained receipts & attachments")).click()
            assertTrue(device.wait(Until.hasObject(By.text("Choose receipt · PDF / JPEG / PNG").enabled(true)),30000));device.findObject(By.text("Choose receipt · PDF / JPEG / PNG")).click()
            assertTrue("Real Android document picker opens",device.wait(Until.hasObject(By.pkg("com.google.android.documentsui")),15000)||device.hasObject(By.pkg("com.android.documentsui")))
            val roots=device.findObject(By.desc("Show roots"))?:device.findObject(By.desc("Open navigation drawer"))
            if(roots!=null){roots.click();assertTrue(device.wait(Until.hasObject(By.text("Downloads")),15000));device.findObject(By.text("Downloads")).click()}
            assertTrue("Synthetic PDF is selectable in the system picker",device.wait(Until.hasObject(By.text(receiptName)),15000));device.findObject(By.text(receiptName)).click()
            scrollTo(device,"Upload receipt");device.findObject(By.text("Upload receipt")).click()
            scrollTo(device,"Archive · retain evidence");assertTrue("Receipt is retained after actual UI upload",device.hasObject(By.text("Archive · retain evidence")));device.findObject(By.text("Archive · retain evidence")).click()
            scrollTo(device,"Show archived receipts");device.findObject(By.text("Show archived receipts")).click()
            scrollTo(device,By.textContains("Archived · retained"),"Archived receipt state");assertTrue(device.hasObject(By.textContains("Archived · retained")))
            val bill=saved.single{it.s("kind")=="purchase_bill"};val evidence=(api.request(api.company(companyIds.getValue(target),"/records/${bill.s("id")}/attachments"))as JSONObject).a("attachments").objects().single()
            assertTrue("UI archive retains evidence",evidence.optBoolean("is_archived"));assertEquals(receiptBytes.size,evidence.optInt("size_bytes"));assertEquals(sha256(receiptBytes),evidence.s("sha256"))
            device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-retained-receipt.png"))
            device.findObject(By.desc("Close")).click();device.pressBack();device.findObject(By.text("More")).click();scrollTo(device,"Settings");device.findObject(By.text("Settings")).click()
            scrollTo(device,"Download backup");device.findObject(By.text("Download backup")).click()
            assertTrue("Complete-backup entry is capability gated and visible",device.wait(Until.hasObject(By.text("Complete company backup")),15000));assertTrue(device.hasObject(By.text("Encrypt saved backup")))
            device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-complete-backup-entry.png"));device.findObject(By.desc("Close")).click()
        } finally { device.executeShellCommand("rm -f '$receiptPath'") }
        api.logout()
    }
}
