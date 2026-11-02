package com.apexbooks.accounting

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.util.Base64
import androidx.test.platform.app.InstrumentationRegistry
import com.apexbooks.accounting.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.File
import java.math.BigDecimal
import java.util.UUID
import java.util.zip.ZipInputStream

/** No Activity, UI input or user's trading company is used. An explicit test option prepares a normal encrypted QA session. */
class NativeHostedAcceptanceTest {
    private fun gstin(prefix:String):String {
        val alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";var sum=0;var factor=2
        for(c in prefix.reversed()){val v=alphabet.indexOf(c)*factor;sum+=v/36+v%36;factor=3-factor}
        return prefix+alphabet[(36-sum%36)%36]
    }
    @Test fun imageAndHostedTransactionPipeline():Unit=runBlocking {
        requireLocalTestOrigin()
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val result=JSONObject();val checks=JSONArray()
        fun check(name:String,condition:Boolean){assertTrue(name,condition);checks.put(name)}
        val original=Bitmap.createBitmap(1600,900,Bitmap.Config.ARGB_8888)
        val random=java.util.Random(71);val pixels=IntArray(1600*900){i->if(i%1600<64||i/1600<64)Color.TRANSPARENT else Color.argb(192,random.nextInt(256),random.nextInt(256),random.nextInt(256))};original.setPixels(pixels,0,1600,0,0,1600,900)
        Canvas(original).apply{drawRect(250f,260f,1350f,640f,Paint().apply{color=Color.rgb(18,124,102)});drawText("NATIVE LOGO QA",350f,490f,Paint().apply{color=Color.WHITE;textSize=95f;isAntiAlias=true})}
        val input=File(context.cacheDir,"native-logo-alpha-qa.png");input.outputStream().use{original.compress(Bitmap.CompressFormat.PNG,100,it)};original.recycle()
        val converted=NativeFiles(context){throw AssertionError(it)}.image(Uri.fromFile(input),900,240000)
        val logoBytes=Base64.decode(converted.substringAfter(','),Base64.DEFAULT)
        check("large transparent logo fits upload limit",logoBytes.size<=240000)
        check("complex logo exercises JPEG fallback",converted.startsWith("data:image/jpeg;base64,"))
        val decoded=BitmapFactory.decodeByteArray(logoBytes,0,logoBytes.size);val corner=decoded.getPixel(0,0)
        check("transparent JPEG corner is white",Color.red(corner)>235&&Color.green(corner)>235&&Color.blue(corner)>235);decoded.recycle()
        result.put("logo_bytes",logoBytes.size)

        val keepSession=InstrumentationRegistry.getArguments().getString("keepSession")=="true"
        val vault=if(keepSession)SessionVault(context)else null
        val origin=BuildConfig.API_ORIGIN
        result.put("api_origin",origin).put("client_version",BuildConfig.VERSION_NAME)
        val stored=vault?.load(origin)
        require(stored==null||stored.s("email").startsWith("native-pipeline-")){"Another user's remembered session exists; leaving it unchanged."}
        val api=ApexApi(origin,vault)
        val email="native-pipeline-${UUID.randomUUID()}@example.invalid";val password="Synthetic-device-only-2026!"
        api.request("/api/auth/register","POST",JSONObject().put("email",email).put("password",password))
        api.login(email,password,keepSession)
        if(keepSession){
            val restored=ApexApi(origin,vault)
            check("normal encrypted QA session restores",restored.restore()&&restored.email==email)
            check("restored QA session reaches its companies",restored.request("/api/companies") is JSONArray)
            context.getExternalFilesDir(null)?.let{File(it,"native-qa-session.json").writeText(JSONObject().put("ready",true).put("synthetic",true).toString())}
        }
        try {
            val company=api.request("/api/companies","POST",JSONObject().put("name","Native Android Transport QA ${System.currentTimeMillis()}").put("tax_mode","regular").put("state_code","27").put("gstin",gstin("27ABCDE1234F1Z")))as JSONObject
            val cid=company.s("id");result.put("company_id",cid)
            fun path(suffix:String)=api.company(cid,suffix)
            val item=api.saveRecord(cid,JSONObject().put("kind","item").put("name","Native device adapter").put("date","2026-11-01").put("data",JSONObject().put("item_type","goods").put("track_stock",true).put("unit","NOS").put("hsn","85176290").put("sale_rate","100").put("purchase_rate","50").put("gst_rate","18")),UUID.randomUUID().toString())
            val itemId=item.s("id")
            api.request(path("/stock/opening"),"POST",JSONObject().put("item_id",itemId).put("date","2026-11-01").put("quantity","10").put("unit_cost","50"),UUID.randomUUID().toString())
            fun body(kind:String,quantity:Int=1,rate:Int=100,tracked:Boolean=false,extra:JSONObject=JSONObject()):JSONObject {
                val supplier=kind in setOf("purchase_bill","purchase_order","debit_note","expense")
                val line=JSONObject().put("description",if(tracked)"Native device adapter"else"Native device service").put("quantity",quantity).put("rate",rate).put("gst_rate",18).put("unit",if(tracked)"NOS"else"OTH").put("hsn",if(tracked)"85176290"else"998313").put("tax_treatment","taxable").put("itc_treatment","pending_review")
                if(tracked)line.put("item_id",itemId)
                val data=JSONObject().put("lines",JSONArray().put(line)).put("place_of_supply","27").put("supplier_state","27")
                if(supplier)data.put("party_gstin",gstin("27PQRST1234L1Z"))
                extra.keys().forEach{data.put(it,extra.get(it))}
                return JSONObject().put("kind",kind).put("name",if(supplier)"Native device supplier"else"Native device buyer").put("date","2026-11-01").put("number","").put("amount","0").put("data",data)
            }
            suspend fun post(value:JSONObject)=api.saveRecord(cid,value,UUID.randomUUID().toString())
            val originalSale=body("sales_invoice",2,100,true);val retry=UUID.randomUUID().toString()
            var sale=api.saveRecord(cid,originalSale,retry)
            check("idempotent native save",api.saveRecord(cid,originalSale,retry).s("id")==sale.s("id"))
            var edited=body("sales_invoice",2,110,true).put("number",sale.s("number"));edited.o("data").put("version",sale.o("data").optInt("version"));sale=api.saveRecord(cid,edited,UUID.randomUUID().toString(),sale)
            check("native invoice edit recalculates GST",sale.decimal("amount").compareTo(BigDecimal("259.60"))==0)
            edited=body("sales_invoice",2,100,true).put("number",sale.s("number"));edited.o("data").put("version",sale.o("data").optInt("version"));sale=api.saveRecord(cid,edited,UUID.randomUUID().toString(),sale)
            val bill=post(body("purchase_bill",10,50,true))
            val convertedDocuments=mutableMapOf<String,JSONObject>()
            for(kind in listOf("estimate","proforma","purchase_order")){
                val draft=post(body(kind));val target=if(kind=="purchase_order")"purchase_bill"else"sales_invoice"
                val posted=post(body(target,extra=JSONObject().put("source_document_id",draft.s("id"))));convertedDocuments[kind]=posted
                check("$kind conversion links source",api.records(cid).first{it.s("id")==draft.s("id")}.s("converted_to").isNotBlank())
            }
            post(body("credit_note",1,100,true,JSONObject().put("applied_to",sale.s("id")).put("return_stock",true)))
            post(body("debit_note",1,50,true,JSONObject().put("applied_to",bill.s("id")).put("return_stock",true)))
            fun payment(kind:String,first:String,second:String):JSONObject=JSONObject().put("kind",kind).put("name",if(kind=="payment_in")"Native device buyer"else"Native device supplier").put("date","2026-11-01").put("amount","100").put("data",JSONObject().put("payment_account","cash").put("allocations",JSONArray().put(JSONObject().put("document_id",first).put("amount","50")).put(JSONObject().put("document_id",second).put("amount","50"))))
            post(payment("payment_in",sale.s("id"),convertedDocuments.getValue("estimate").s("id")))
            post(body("pos",extra=JSONObject().put("payment_account","cash").put("tender_amount","118")))
            val bank=api.request(path("/bank-accounts"),"POST",JSONObject().put("name","Native device QA bank").put("account_hint","0000"))as JSONObject
            for(direction in listOf("cash_to_bank","bank_to_cash"))post(JSONObject().put("kind","bank_transfer").put("name","Native QA $direction").put("date","2026-11-01").put("amount","20").put("data",JSONObject().put("direction",direction).put("bank_account_id",bank.s("id"))))
            post(payment("payment_out",bill.s("id"),convertedDocuments.getValue("purchase_order").s("id")))
            post(body("expense",extra=JSONObject().put("payment_account","cash")))
            val register=api.records(cid)
            check("split receipt plus credit reduces invoice balance",register.first{it.s("id")==sale.s("id")}.decimal("outstanding").compareTo(BigDecimal("68"))==0)
            check("split payment plus debit reduces bill balance",register.first{it.s("id")==bill.s("id")}.decimal("outstanding").compareTo(BigDecimal("481"))==0)

            api.request(path("/document-branding"),"PATCH",JSONObject().put("logo",converted).put("phone","0000000000"))
            val branding=api.request(path("/document-branding"),"PUT",JSONObject().put("bank_name","Synthetic native bank"))as JSONObject
            check("native PATCH and partial PUT preserve logo",branding.s("logo")==converted)
            val pdf=api.bytes(path("/documents/${sale.s("id")}.pdf"))
            check("native PDF download",pdf.take(5).toByteArray().toString(Charsets.US_ASCII)=="%PDF-")
            val pdfFile=File(context.cacheDir,"native-logo-document.pdf");pdfFile.writeBytes(pdf)
            PdfRenderer(ParcelFileDescriptor.open(pdfFile,ParcelFileDescriptor.MODE_READ_ONLY)).use{renderer->
                check("Android PDF renderer opens document",renderer.pageCount>0)
                renderer.openPage(0).use{page->
                    val preview=Bitmap.createBitmap(1000,1000*page.height/page.width,Bitmap.Config.ARGB_8888);preview.eraseColor(Color.WHITE)
                    page.render(preview,null,null,PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    context.getExternalFilesDir(null)?.let{folder->File(folder,"native-logo-document.png").outputStream().use{preview.compress(Bitmap.CompressFormat.PNG,100,it)};File(folder,"native-logo-document.pdf").writeBytes(pdf)}
                    preview.recycle()
                }
            }
            val query="?from_date=2026-11-01&to_date=2026-11-30"
            val financial=api.request(path("/reports/financial$query"))as JSONObject
            check("native posted ledger balances",financial.decimal("balance_difference").signum()==0)
            val controls=financial.a("accounts").objects().associate{it.s("code")to it.decimal("closing_balance")}
            for((code,expected)in mapOf("SYS-AR" to "254","SYS-AP" to "549","SYS-INVENTORY" to "900","SYS-CASH" to "0","SYS-COGS" to "50","SYS-SALES" to "400","SYS-IN-CGST" to "58.50","SYS-IN-SGST" to "58.50","SYS-OUT-CGST" to "36","SYS-OUT-SGST" to "36"))check("ledger control $code",controls.getValue(code).compareTo(BigDecimal(expected))==0)
            check("profit after stock cost, returns and expenses",financial.decimal("net_profit").compareTo(BigDecimal("150"))==0)
            val stock=api.request(path("/reports/stock$query"))as JSONObject
            val tracked=stock.a("rows").objects().first{it.s("item_id")==itemId}
            check("stock quantities include both returns",tracked.decimal("closing_quantity").compareTo(BigDecimal("18"))==0)
            check("moving-average stock value reconciles",tracked.decimal("closing_value").compareTo(BigDecimal("900"))==0)
            result.put("financial",financial).put("stock",stock)
            val summary=api.request(path("/reports/summary$query"))as JSONObject
            check("posted sales net of credit and drafts",summary.decimal("sales").compareTo(BigDecimal("472"))==0)
            check("posted purchases net of debit and drafts",summary.decimal("purchases").compareTo(BigDecimal("649"))==0)
            result.put("summary",summary)
            for(kind in listOf("gstr1","gstr2a","gstr3b")){
                api.request(path("/gst-returns/$kind$query"))
                for(format in listOf("pdf","xlsx")){
                    val bytes=api.bytes(path("/gst-returns/$kind.$format$query"))
                    check("$kind $format download",if(format=="pdf")bytes.take(5).toByteArray().toString(Charsets.US_ASCII)=="%PDF-"else bytes.take(2)==listOf(80.toByte(),75.toByte()))
                    if(format=="xlsx"){var workbook="";ZipInputStream(ByteArrayInputStream(bytes)).use{zip->var entry=zip.nextEntry;while(entry!=null){if(entry.name=="xl/workbook.xml")workbook=zip.readBytes().toString(Charsets.UTF_8);entry=zip.nextEntry}};check("$kind contains worksheet schedules",workbook.contains("<sheet "))}
                }
            }
            val draft=api.request(path("/gst-returns/gstr1.json$query"))as JSONObject
            check("GSTR-1 JSON contains GSTIN and consumer schedules",draft.s("gstin")==company.s("gstin")&&draft.a("b2cs").length()>0)
            result.put("checks",checks).put("all_pass",true)
            File(context.cacheDir,"native-http-acceptance.json").writeText(result.toString(2))
            context.getExternalFilesDir(null)?.let{File(it,"native-http-acceptance.json").writeText(result.toString(2))}
        }finally{if(!keepSession)api.logout()}
    }
}
