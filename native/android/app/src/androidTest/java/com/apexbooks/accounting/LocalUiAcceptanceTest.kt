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

    private fun dismissVisibleKeyboard(device:UiDevice){
        // A system picker can restore focus to the company-name field and reopen
        // Gboard. Never swipe through a keyboard: that can gesture-type into data.
        device.waitForIdle()
        val keyboard=By.pkg(java.util.regex.Pattern.compile("com\\.(google\\.android|android)\\.inputmethod\\.latin"))
        if(device.hasObject(keyboard)){
            device.pressBack()
            assertTrue("Visible keyboard dismissed before form scrolling",device.wait(Until.gone(keyboard),10000))
            device.waitForIdle()
        }
    }
    private fun scrollTo(device:UiDevice,text:String)=scrollTo(device,By.text(text),text)
    private fun scrollTo(device:UiDevice,selector:BySelector,label:String) {
        dismissVisibleKeyboard(device)
        if(device.wait(Until.hasObject(selector),2000))return
        repeat(8){dismissVisibleKeyboard(device);if(device.hasObject(selector))return;device.swipe(device.displayWidth/2,device.displayHeight*3/4,device.displayWidth/2,device.displayHeight/4,30);device.waitForIdle()}
        // A previous action can leave the same form scrolled below its next control.
        repeat(16){dismissVisibleKeyboard(device);if(device.hasObject(selector))return;device.swipe(device.displayWidth/2,device.displayHeight/4,device.displayWidth/2,device.displayHeight*3/4,30);device.waitForIdle()}
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
        if(roots!=null){
            roots.click()
            // Downloads is also the toolbar title when reopening the picker.
            // Select the drawer row, never an identically named background label.
            val rootsList=By.res(pkg,"roots_list")
            assertTrue("Native picker roots drawer opens",device.wait(Until.hasObject(rootsList),15000))
            val downloads=device.findObject(rootsList).findObject(By.text("Downloads"))
            assertNotNull("Downloads root row exists inside the drawer",downloads)
            downloads.click()
            assertTrue("Native picker roots drawer closes before file selection",device.wait(Until.gone(rootsList),15000))
        }
        device.waitForIdle()
        return pkg
    }
    private fun awaitReadyAction(device:UiDevice,text:String){
        scrollTo(device,text)
        assertTrue("Action is ready: $text",device.wait(Until.hasObject(By.text(text).enabled(true)),60000))
    }
    private fun clickReadyAction(device:UiDevice,text:String){
        awaitReadyAction(device,text)
        clickStableControl(device,By.text(text),text)
    }
    private fun clickReadyDescription(device:UiDevice,description:String){
        val selector=By.desc(description)
        scrollTo(device,selector,description)
        assertTrue("Visible control: $description",device.wait(Until.hasObject(selector),30000))
        clickStableControl(device,selector,description)
    }
    private fun clickStableControl(device:UiDevice,selector:BySelector,label:String){
        // Compose may expose a non-clickable TextView inside the actual action.
        // Wait for scroll/layout settling and activate that real clickable ancestor
        // once; never repeat a financial action after an uncertain outcome.
        device.waitForIdle()
        val deadline=android.os.SystemClock.uptimeMillis()+10000
        var previous:android.graphics.Rect?=null
        var stable=0
        while(android.os.SystemClock.uptimeMillis()<deadline){
            // UIAutomator can report a background button as visible underneath
            // Gboard. A late IME animation must not turn Create into a keypress.
            val keyboard=By.pkg(java.util.regex.Pattern.compile("com\\.(google\\.android|android)\\.inputmethod\\.latin"))
            if(device.hasObject(keyboard)){
                dismissVisibleKeyboard(device);previous=null;stable=0
                continue
            }
            var target=device.findObject(selector)
            while(target!=null&&!target.isClickable)target=target.parent
            if(target!=null&&target.isEnabled){
                val bounds=target.visibleBounds
                if(bounds.width()>0&&bounds.height()>0&&bounds==previous)stable++ else stable=0
                previous=android.graphics.Rect(bounds)
                if(stable>=3){target.click();return}
            }else{stable=0;previous=null}
            android.os.SystemClock.sleep(150)
        }
        fail("No stable visible clickable action: $label")
    }
    private fun typeOnlyPassword(device:UiDevice,password:String){
        // Export has only a password; restore has the name followed by its password.
        // The caller first scrolls to the actual password label, so the final visible
        // editable field is the password rather than an offscreen name field.
        val fields=device.findObjects(By.clazz("android.widget.EditText"))
        assertTrue("Visible backup password field",fields.size in 1..2)
        fields.last().click();fields.last().text=password;device.pressBack()
    }
    private fun setNamedEdit(device:UiDevice,label:String,value:String){
        scrollTo(device,label)
        val selector=By.clazz("android.widget.EditText").hasDescendant(By.text(label))
        assertTrue("Editable field: $label",device.wait(Until.hasObject(selector),10000))
        val field=device.findObject(selector);assertTrue(field.isEnabled);field.click();field.text=value
        dismissVisibleKeyboard(device)
        assertTrue("Exact entered value retained: $label",device.wait(Until.hasObject(By.clazz("android.widget.EditText").text(value)),10000))
    }
    private fun chooseSavedParty(device:UiDevice){
        val selector=By.desc("Saved party · Enter manually")
        scrollTo(device,selector,"Saved party selector")
        assertTrue("Saved party is an accessible clickable control",device.findObject(selector).isClickable)
        device.findObject(selector).click()
        clickReadyAction(device,"UI Smoke Buyer")
        // Selection updates the form before the modal finishes dismissing.
        // Wait for both real arrival states before invoking the next page action.
        assertTrue("Saved party sheet dismissed",device.wait(Until.gone(By.text("Saved party")),15000))
        assertTrue("Selected party reflected in retained document",device.wait(Until.hasObject(By.desc("Saved party · UI Smoke Buyer")),15000))
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
        clickReadyAction(device,"Low stock & reorder review")
        assertTrue("Reorder report loaded",device.wait(Until.hasObject(By.textContains("items at or below threshold")),30000))
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-reorder-open.png"))
        scrollTo(device,"UI Reorder Item")
        assertTrue("Exact seeded low-stock item is visible after scrolling",device.hasObject(By.text("UI Reorder Item")))
        clickReadyAction(device,"Review purchase order · 1 items")
        assertTrue(device.wait(Until.hasObject(By.text("New Purchase Order")),15000))
        chooseSavedParty(device)
        clickReadyAction(device,"Next: add items")
        // Seeded lines open collapsed; expand the real visible card before inspecting its fields.
        assertTrue("Reorder draft shows the selected item card",device.wait(Until.hasObject(By.text("UI Reorder Item")),15000))
        device.findObject(By.text("UI Reorder Item")).click()
        assertTrue("Reorder draft preserves the selected item",device.wait(Until.hasObject(By.desc("Item / service · UI Reorder Item")),15000))
        clickReadyAction(device,"Check this party’s item prices")
        scrollTo(device,"Last posted price for this exact party and item.");assertTrue(device.hasObject(By.text("Last posted price for this exact party and item.")))
        clickReadyAction(device,"Apply suggested price & tax basis")
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-reorder-price-review.png"))
        clickReadyDescription(device,"Close entry")
        clickReadyAction(device,"Discard draft")
        assertTrue("Discard confirmation closes",device.wait(Until.gone(By.text("Discard draft")),15000))
        assertTrue("Purchase order editor closes after discard",device.wait(Until.gone(By.text("New Purchase Order")),15000))
        clickReadyAction(device,"New invoice")
        assertTrue(device.wait(Until.hasObject(By.text("New Sales Invoice")),15000))
        chooseSavedParty(device)
        clickReadyAction(device,"Check party payment terms")
        clickReadyAction(device,"Use suggested due date")
        scrollTo(device,By.desc("Due date · optional · "+java.time.LocalDate.parse(today()).plusDays(30).toString()),"Applied due date")
        assertTrue("Explicit terms Apply sets the suggested date",device.hasObject(By.desc("Due date · optional · "+java.time.LocalDate.parse(today()).plusDays(30).toString())))
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-party-terms-review.png"))
        clickReadyDescription(device,"Close entry")
        clickReadyAction(device,"Keep editing")
        assertTrue("Keep editing closes only the confirmation",device.wait(Until.gone(By.text("Keep editing")),15000))
        assertTrue("Keep editing retains the invoice editor",device.wait(Until.hasObject(By.text("New Sales Invoice")),15000))
        clickReadyDescription(device,"Close entry")
        clickReadyAction(device,"Discard draft")
        assertTrue("Discard confirmation closes",device.wait(Until.gone(By.text("Discard draft")),15000))
        assertTrue("Discarded invoice editor closes",device.wait(Until.gone(By.text("New Sales Invoice")),15000))
        val afterReview=api.records(companyIds.getValue(target))
        assertEquals("Reviewing suggestions creates no purchase order",0,afterReview.count{it.s("kind")=="purchase_order"})
        assertEquals("Discarded terms review creates no new invoice",1,afterReview.count{it.s("kind")=="sales_invoice"})
        // Create a real second invoice entirely through the native document editor.
        clickReadyAction(device,"New invoice")
        assertTrue("Blank document asks for item details instead of claiming an active calculation",device.wait(Until.hasObject(By.text("Add item details")),10000))
        assertTrue(device.wait(Until.hasObject(By.text("New Sales Invoice")),15000))
        chooseSavedParty(device)
        clickReadyAction(device,"Next: add items")
        val itemSelector=By.desc("Item / service · Enter a description");scrollTo(device,itemSelector,"Item / service selector");device.findObject(itemSelector).click()
        clickReadyAction(device,"UI Reorder Item")
        assertTrue("Item selection sheet closes",device.wait(Until.gone(By.text("Item / service")),15000))
        assertTrue("Chosen item remains on invoice",device.wait(Until.hasObject(By.desc("Item / service · UI Reorder Item")),15000))
        clickReadyAction(device,"Review document")
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
        // Inline master creation must leave the same unsaved invoice and its math intact.
        val inlineParty="UI Inline Customer ${UUID.randomUUID().toString().take(6)}"
        val inlineItem="UI Inline Service ${UUID.randomUUID().toString().take(6)}"
        val financialBefore=canonical(api.request(api.company(companyIds.getValue(target),"/reports/financial?from_date=1900-01-01&to_date=${today()}")))
        clickReadyAction(device,"New invoice")
        clickReadyAction(device,"Create customer & use")
        setNamedEdit(device,"Name",inlineParty)
        clickReadyAction(device,"Create & use")
        assertTrue("Inline customer dialog closes",device.wait(Until.gone(By.text("Create customer for this invoice")),30000))
        assertTrue("Returned customer selected on retained invoice",device.wait(Until.hasObject(By.clazz("android.widget.EditText").text(inlineParty)),15000))
        clickReadyAction(device,"Next: add items")
        setNamedEdit(device,"Description","Retained draft line")
        setNamedEdit(device,"Quantity","3");setNamedEdit(device,"Rate (₹)","100")
        clickReadyDescription(device,"Line discount · Percentage (%)")
        clickReadyAction(device,"Fixed amount (₹)")
        assertTrue("Discount mode sheet closes",device.wait(Until.gone(By.text("Line discount")),15000))
        assertTrue("Fixed discount mode selected",device.wait(Until.hasObject(By.desc("Line discount · Fixed amount (₹)")),15000))
        setNamedEdit(device,"Discount (₹)","10")
        clickReadyAction(device,"Create item & use")
        setNamedEdit(device,"Name",inlineItem)
        clickReadyDescription(device,"Type · Goods");clickReadyAction(device,"Services")
        assertTrue("Item type sheet closes",device.wait(Until.gone(By.text("Type")),15000))
        assertTrue("Service type selected",device.wait(Until.hasObject(By.desc("Type · Services")),15000))
        setNamedEdit(device,"Sale price (₹)","25")
        clickReadyAction(device,"Create & use")
        assertTrue("Inline item dialog closes",device.wait(Until.gone(By.text("Create item for this invoice")),30000))
        clickReadyAction(device,"Review document")
        scrollTo(device,"Retained draft line × 3");scrollTo(device,"$inlineItem × 1")
        assertTrue("Retained quantity/fixed discount plus new service preview totals315",device.wait(Until.hasObject(By.text(money("315"))),30000))
        val inlineRows=api.records(companyIds.getValue(target))
        assertEquals(1,inlineRows.count{it.s("kind")=="party"&&it.s("name")==inlineParty})
        val service=inlineRows.single{it.s("kind")=="item"&&it.s("name")==inlineItem}
        assertEquals("services",service.o("data").s("item_type"));assertFalse(service.o("data").optBoolean("track_stock"))
        assertEquals("Inline masters alone post no invoice",2,inlineRows.count{it.s("kind")=="sales_invoice"})
        assertEquals("Inline masters do not change financial reports",financialBefore,canonical(api.request(api.company(companyIds.getValue(target),"/reports/financial?from_date=1900-01-01&to_date=${today()}"))))
        device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-inline-master-review.png"))
        clickReadyDescription(device,"Close entry");clickReadyAction(device,"Discard draft")
        assertTrue("Original invoice editor closes only on explicit discard",device.wait(Until.gone(By.text("New Sales Invoice")),15000))
        assertEquals("Discarding inline review posts no invoice",2,api.records(companyIds.getValue(target)).count{it.s("kind")=="sales_invoice"})
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
            device.findObject(By.text("More")).click();clickReadyAction(device,"Purchase bills")
            assertTrue("Purchase register arrived after menu navigation",device.wait(Until.hasObject(By.text("UI Smoke Buyer")),30000));clickReadyAction(device,"UI Smoke Buyer")
            clickReadyAction(device,"Retained receipts & attachments")
            assertTrue(device.wait(Until.hasObject(By.text("Choose receipt · PDF / JPEG / PNG").enabled(true)),30000));device.findObject(By.text("Choose receipt · PDF / JPEG / PNG")).click()
            val receiptPickerPackage=documentPickerDownloads(device)
            assertTrue("Synthetic PDF is selectable in the system picker",device.wait(Until.hasObject(By.text(receiptName)),15000));device.findObject(By.text(receiptName)).click()
            assertTrue("Receipt picker returns to the app",device.wait(Until.gone(By.pkg(receiptPickerPackage)),15000))
            clickReadyAction(device,"Upload receipt")
            scrollTo(device,"Archive · retain evidence");assertTrue("Receipt is retained after actual UI upload",device.hasObject(By.text("Archive · retain evidence")));device.findObject(By.text("Archive · retain evidence")).click()
            clickReadyAction(device,"Show archived receipts")
            scrollTo(device,By.textContains("Archived · retained"),"Archived receipt state");assertTrue(device.hasObject(By.textContains("Archived · retained")))
            val bill=saved.single{it.s("kind")=="purchase_bill"};val evidence=(api.request(api.company(companyIds.getValue(target),"/records/${bill.s("id")}/attachments"))as JSONObject).a("attachments").objects().single()
            assertTrue("UI archive retains evidence",evidence.optBoolean("is_archived"));assertEquals(receiptBytes.size,evidence.optInt("size_bytes"));assertEquals(sha256(receiptBytes),evidence.s("sha256"))
            device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-retained-receipt.png"))
            clickReadyDescription(device,"Close")
            assertTrue("Receipt dialog closed",device.wait(Until.gone(By.desc("Close")),15000))
            clickReadyDescription(device,"Close transaction")
            assertTrue("Purchase detail closed",device.wait(Until.gone(By.desc("Close transaction")),15000))
            clickReadyAction(device,"More");clickReadyAction(device,"Settings")
            clickReadyAction(device,"Download backup")
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
                clickReadyAction(device,"Prepare complete backup")
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
                clickReadyDescription(device,"Close")
                assertTrue("Export dialog closed after saved file",device.wait(Until.gone(By.desc("Close")),15000))
                clickReadyAction(device,"Restore company backup")
                assertTrue(device.wait(Until.hasObject(By.text("Restore complete portable backup")),15000))
                scrollTo(device,"New company name")
                val nameFields=device.findObjects(By.clazz("android.widget.EditText"));assertEquals("New company name field",1,nameFields.size)
                nameFields.single().click();nameFields.single().text=restoredName;device.pressBack()
                clickReadyAction(device,"Choose backup file")
                val restorePickerPackage=documentPickerDownloads(device)
                assertTrue("Saved encrypted file is offered by the real picker",device.wait(Until.hasObject(By.text(backupName)),15000));device.findObject(By.text(backupName)).click()
                assertTrue("Encrypted backup picker returns to the app",device.wait(Until.gone(By.pkg(restorePickerPackage)),15000))
                dismissVisibleKeyboard(device)
                assertTrue("Picker return preserves the exact new company name",device.hasObject(By.clazz("android.widget.EditText").text(restoredName)))
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
                assertTrue("Restore dialog dismissed",device.wait(Until.gone(By.text("Restore complete portable backup")),15000))
                clickReadyAction(device,"Transactions")
                assertTrue("Restored company history loaded into the actual register",device.wait(Until.hasObject(By.text("UI Smoke Buyer")),30000))
                device.takeScreenshot(File(context.getExternalFilesDir(null),"local-native-restored-company.png"))
            } finally { device.executeShellCommand("rm -f '/sdcard/Download/$backupName'") }
        } finally { resolver.delete(receiptUri,null,null) }
        api.logout()
    }
}
