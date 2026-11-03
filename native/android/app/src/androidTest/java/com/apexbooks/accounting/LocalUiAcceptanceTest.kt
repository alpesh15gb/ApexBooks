package com.apexbooks.accounting

import android.content.ContentValues
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
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
    private fun canonical(value:Any?):String=when(value){
        is JSONObject->value.keys().asSequence().toList().sorted().joinToString(prefix="{",postfix="}"){JSONObject.quote(it)+":"+canonical(value.get(it))}
        is JSONArray->(0 until value.length()).joinToString(prefix="[",postfix="]"){canonical(value.get(it))}
        is String->JSONObject.quote(value)
        else->value?.toString()?:"null"
    }
    private fun documentPickerDownloads(device:UiDevice):String {
        assertTrue("Real Android document picker opens",device.wait(Until.hasObject(By.pkg("com.google.android.documentsui")),15000)||device.hasObject(By.pkg("com.android.documentsui")))
        val pkg=if(device.hasObject(By.pkg("com.google.android.documentsui")))"com.google.android.documentsui"else"com.android.documentsui"
        val roots=device.findObject(By.desc("Show roots"))?:device.findObject(By.desc("Open navigation drawer"))
        if(roots!=null){roots.click();assertTrue(device.wait(Until.hasObject(By.text("Downloads")),15000));device.findObject(By.text("Downloads")).click()}
        return pkg
    }
    private fun awaitReadyAction(device:UiDevice,text:String){
        scrollTo(device,text)
        assertTrue("Action is ready: $text",device.wait(Until.hasObject(By.text(text).enabled(true)),60000))
    }
    private fun clickReadyAction(device:UiDevice,text:String){
        awaitReadyAction(device,text)
        device.findObject(By.text(text).enabled(true)).click()
    }
    private fun typeOnlyPassword(device:UiDevice,password:String){
        // Export has only a password; restore has the name followed by its password.
        // The caller first scrolls to the actual password label, so the final visible
        // editable field is the password rather than an offscreen name field.
        val fields=device.findObjects(By.clazz("android.widget.EditText"))
        assertTrue("Visible backup password field",fields.size in 1..2)
        fields.last().click();fields.last().text=password;device.pressBack()
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
        // Seeded lines open collapsed; expand the real visible card before inspecting its fields.
        assertTrue("Reorder draft shows the selected item card",device.wait(Until.hasObject(By.text("UI Reorder Item")),15000))
        device.findObject(By.text("UI Reorder Item")).click()
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
        val receiptBytes="%PDF-1.4\n% Synthetic Android UI receipt\n%%EOF\n".toByteArray()
        require(Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) { "Local receipt UI fixture requires the API 29+ test device." }
        // Publish a real Downloads document. A raw adb file is not registered with
        // Android's Downloads provider and can be absent from the system picker.
        val resolver=context.contentResolver
        val receiptUri=requireNotNull(resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME,receiptName)
            put(MediaStore.MediaColumns.MIME_TYPE,"application/pdf")
            put(MediaStore.MediaColumns.RELATIVE_PATH,Environment.DIRECTORY_DOWNLOADS)
            put(MediaStore.MediaColumns.IS_PENDING,1)
        })) { "Create synthetic Downloads fixture" }
        try {
            requireNotNull(resolver.openOutputStream(receiptUri)).use { it.write(receiptBytes) }
            assertEquals("Publish synthetic receipt to Downloads",1,resolver.update(receiptUri,ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING,0) },null,null))
            requireNotNull(resolver.openInputStream(receiptUri)).use { assertArrayEquals("Published fixture bytes",receiptBytes,it.readBytes()) }
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
            device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-complete-backup-entry.png"))
            val sourceId=companyIds.getValue(target)
            val period="?from_date=1900-01-01&to_date=${today()}"
            val reportPaths=listOf("/reports/summary$period","/reports/financial$period")
            val sourceReports=reportPaths.associateWith{canonical(api.request(api.company(sourceId,it)))}
            val sourceRecords=canonical(JSONArray(api.records(sourceId).sortedBy{it.s("id")}))
            val companiesBefore=(api.request("/api/companies")as JSONArray).objects().map{it.s("id")}.toSet()
            val backupName="apex-ui-roundtrip-${UUID.randomUUID()}.apexbackup"
            val backupPassword="Synthetic-backup-only-2026!"
            val restoredName="UI Restored ${UUID.randomUUID().toString().take(8)}"
            try {
                // Exercise the app's streaming encryption and actual Android save picker.
                scrollTo(device,"Encryption password · at least 12 characters");typeOnlyPassword(device,backupPassword)
                scrollTo(device,"Prepare complete backup");device.findObject(By.text("Prepare complete backup")).click()
                scrollTo(device,"Complete backup verified and ready to save. It includes archived receipts.")
                clickReadyAction(device,"Save verified backup file")
                val pickerPackage=documentPickerDownloads(device)
                val filenameFields=device.findObjects(By.pkg(pickerPackage).clazz("android.widget.EditText"))
                assertEquals("Native save picker filename field",1,filenameFields.size)
                filenameFields.single().click();filenameFields.single().text=backupName;device.pressBack()
                val save=By.pkg(pickerPackage).res("android:id/button1").enabled(true)
                assertTrue("Native save action is enabled",device.wait(Until.hasObject(save),15000));device.findObject(save).click()
                assertTrue("Encrypted backup saved through the real picker",device.wait(Until.hasObject(By.text("Complete backup verified and saved to your selected location.")),30000))
                device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-encrypted-backup-saved.png"))
                device.findObject(By.desc("Close")).click()
                scrollTo(device,"Restore company backup");device.findObject(By.text("Restore company backup")).click()
                assertTrue(device.wait(Until.hasObject(By.text("Restore complete portable backup")),15000))
                scrollTo(device,"New company name")
                val nameFields=device.findObjects(By.clazz("android.widget.EditText"));assertEquals("New company name field",1,nameFields.size)
                nameFields.single().click();nameFields.single().text=restoredName;device.pressBack()
                scrollTo(device,"Choose backup file");device.findObject(By.text("Choose backup file")).click()
                documentPickerDownloads(device)
                assertTrue("Saved encrypted file is offered by the real picker",device.wait(Until.hasObject(By.text(backupName)),15000));device.findObject(By.text(backupName)).click()
                scrollTo(device,"Encrypted backup detected. Authenticate locally before any upload.")
                awaitReadyAction(device,"Authenticate, upload & validate")
                scrollTo(device,"Backup password · local only");typeOnlyPassword(device,backupPassword)
                clickReadyAction(device,"Authenticate, upload & validate")
                scrollTo(device,"Review before creating the new company")
                assertEquals("Preview creates no company",companiesBefore,(api.request("/api/companies")as JSONArray).objects().map{it.s("id")}.toSet())
                device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-restore-preview.png"))
                clickReadyAction(device,"Confirm restore into new company")
                scrollTo(device,"Open restored company")
                val companiesAfter=(api.request("/api/companies")as JSONArray).objects()
                val restored=companiesAfter.single{it.s("name")==restoredName};val restoredId=restored.s("id")
                assertTrue("Restore uses a new company identity",restoredId !in companiesBefore)
                assertEquals("Exactly one company created after explicit confirmation",companiesBefore+restoredId,companiesAfter.map{it.s("id")}.toSet())
                for(path in reportPaths){
                    assertEquals("Restored canonical report $path",sourceReports.getValue(path),canonical(api.request(api.company(restoredId,path))))
                    assertEquals("Original company report unchanged $path",sourceReports.getValue(path),canonical(api.request(api.company(sourceId,path))))
                }
                assertEquals("Original records unchanged",sourceRecords,canonical(JSONArray(api.records(sourceId).sortedBy{it.s("id")})))
                val restoredBill=api.records(restoredId).single{it.s("kind")=="purchase_bill"}
                val restoredEvidence=(api.request(api.company(restoredId,"/records/${restoredBill.s("id")}/attachments"))as JSONObject).a("attachments").objects().single()
                assertTrue("Archived evidence survives encrypted UI roundtrip",restoredEvidence.optBoolean("is_archived"))
                assertEquals(receiptBytes.size,restoredEvidence.optInt("size_bytes"));assertEquals(sha256(receiptBytes),restoredEvidence.s("sha256"))
                assertArrayEquals("Restored receipt exact bytes",receiptBytes,api.rawBytes(api.company(restoredId,"/attachments/${restoredEvidence.s("id")}/download"),maximumResponse=2*1024*1024))
                assertArrayEquals("Original receipt exact bytes unchanged",receiptBytes,api.rawBytes(api.company(sourceId,"/attachments/${evidence.s("id")}/download"),maximumResponse=2*1024*1024))
                val originalEvidence=(api.request(api.company(sourceId,"/records/${bill.s("id")}/attachments"))as JSONObject).a("attachments").objects().single()
                assertEquals("Original archived receipt metadata unchanged",canonical(evidence),canonical(originalEvidence))
                clickReadyAction(device,"Open restored company")
                assertTrue("Explicitly opened new company",device.wait(Until.hasObject(By.text(restoredName)),30000))
                device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-restored-company.png"))
            } finally { device.executeShellCommand("rm -f '/sdcard/Download/$backupName'") }
        } finally { resolver.delete(receiptUri,null,null) }
        api.logout()
    }
}
