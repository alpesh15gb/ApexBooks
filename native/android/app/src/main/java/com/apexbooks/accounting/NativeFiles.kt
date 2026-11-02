package com.apexbooks.accounting

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.print.*
import android.print.pdf.PrintedPdfDocument
import android.util.Base64
import androidx.core.content.FileProvider
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.SecureRandom
import java.util.UUID
import java.util.concurrent.Executors
import java.util.zip.GZIPOutputStream
import javax.crypto.Cipher
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

class NativeFiles(private val context:Context,private val error:(String)->Unit) {
    var launchOpen:((Array<String>)->Unit)?=null;var launchSave:((String)->Unit)?=null;var launchCamera:((Uri)->Unit)?=null
    private var chosen:((Uri)->Unit)?=null;private var camera:((Uri)->Unit)?=null;private var cameraUri:Uri?=null
    private var export:ByteArray?=null
    private var exportFile:File?=null
    private var exportFinished:((Boolean)->Unit)?=null
    val privateStaging:File=File(context.cacheDir,"portable-staging").apply{mkdirs();val expired=System.currentTimeMillis()-24L*60*60*1000;listFiles()?.filter{it.isFile&&it.name.endsWith(".part")&&it.lastModified()<expired}?.forEach{it.delete()}}
    fun displayName(uri:Uri):String=context.contentResolver.query(uri,arrayOf(android.provider.OpenableColumns.DISPLAY_NAME),null,null,null)?.use{if(it.moveToFirst())it.getString(0)else null}?:"receipt"
    fun mediaType(uri:Uri)=context.contentResolver.getType(uri).orEmpty()
    suspend fun stage(uri:Uri,maximum:Long):File=withContext(Dispatchers.IO){val file=java.nio.file.Files.createTempFile(privateStaging.toPath(),"selected-",".part").toFile();try{context.contentResolver.openInputStream(uri)?.use{input->file.outputStream().use{out->val buffer=ByteArray(65536);var total=0L;while(true){currentCoroutineContext().ensureActive();val n=input.read(buffer);if(n<0)break;total+=n;if(total>maximum)throw Exception("The selected backup exceeds the supported size.");out.write(buffer,0,n)}}}?:throw Exception("The selected file cannot be read.");file}catch(e:Exception){file.delete();throw e}}
    fun pick(types:Array<String> = arrayOf("*/*"),callback:(Uri)->Unit){chosen=callback;launchOpen?.invoke(types)?:error("The file picker is unavailable.")}
    fun picked(uri:Uri?){val callback=chosen;chosen=null;if(uri!=null)callback?.invoke(uri)}
    fun capture(callback:(Uri)->Unit){val directory=File(context.cacheDir,"captures").apply{mkdirs()};val file=File(directory,"${UUID.randomUUID()}.jpg");cameraUri=FileProvider.getUriForFile(context,context.packageName+".files",file);camera=callback;launchCamera?.invoke(cameraUri!!)?:error("A camera application is unavailable.")}
    fun captured(success:Boolean){val uri=cameraUri;val callback=camera;camera=null;cameraUri=null;if(success&&uri!=null)callback?.invoke(uri)}
    fun save(bytes:ByteArray,name:String){exportFile=null;exportFinished=null;export=bytes;launchSave?.invoke(name.replace(Regex("[\\\\/:*?\"<>|]"),"_"))?:error("The save picker is unavailable.")}
    fun saveFile(file:File,name:String,finished:(Boolean)->Unit){export=null;exportFile=file;exportFinished=finished;launchSave?.invoke(name.replace(Regex("[\\\\/:*?\"<>|]"),"_"))?:run{exportFile=null;exportFinished=null;error("The save picker is unavailable.");finished(false)}}
    suspend fun saved(uri:Uri?){val content=export;val source=exportFile;val callback=exportFinished;export=null;exportFile=null;exportFinished=null;try{if(uri!=null&&(content!=null||source!=null))withContext(Dispatchers.IO){context.contentResolver.openOutputStream(uri,"wt")?.use{out->if(source!=null)source.inputStream().use{input->val buffer=ByteArray(65536);while(true){currentCoroutineContext().ensureActive();val n=input.read(buffer);if(n<0)break;out.write(buffer,0,n)}}else out.write(content!!)}?:throw Exception("The selected file could not be written.")};callback?.invoke(uri!=null)}catch(e:Exception){callback?.invoke(false);throw e}}
    suspend fun read(uri:Uri,maximum:Int=50_000_000):ByteArray=withContext(Dispatchers.IO){context.contentResolver.openInputStream(uri)?.use{input->val out=ByteArrayOutputStream();val buffer=ByteArray(16384);while(true){val size=input.read(buffer);if(size<0)break;if(out.size()+size>maximum)throw Exception("The file exceeds the supported size.");out.write(buffer,0,size)};out.toByteArray()}?:throw Exception("The selected file could not be read.")}
    suspend fun image(uri:Uri,maximumDimension:Int=600,maximumBytes:Int=64000):String=withContext(Dispatchers.IO){
        val input=read(uri,15_000_000);val bounds=BitmapFactory.Options().apply{inJustDecodeBounds=true};BitmapFactory.decodeByteArray(input,0,input.size,bounds);if(bounds.outWidth<=0||bounds.outHeight<=0||bounds.outWidth>24000||bounds.outHeight>24000)throw Exception("Choose a supported PNG, JPEG or WebP image.")
        var sample=1;while(maxOf(bounds.outWidth,bounds.outHeight)/sample>maximumDimension*2)sample*=2
        var bitmap=BitmapFactory.decodeByteArray(input,0,input.size,BitmapFactory.Options().apply{inSampleSize=sample})?:throw Exception("The image could not be decoded.")
        val factor=maximumDimension.toFloat()/maxOf(bitmap.width,bitmap.height);if(factor<1){val scaled=Bitmap.createScaledBitmap(bitmap,(bitmap.width*factor).toInt().coerceAtLeast(1),(bitmap.height*factor).toInt().coerceAtLeast(1),true);if(scaled!==bitmap)bitmap.recycle();bitmap=scaled}
        val orientation=runCatching{android.media.ExifInterface(java.io.ByteArrayInputStream(input)).getAttributeInt(android.media.ExifInterface.TAG_ORIENTATION,1)}.getOrDefault(1)
        if(orientation in 2..8){val matrix=android.graphics.Matrix();when(orientation){2->matrix.setScale(-1f,1f);3->matrix.setRotate(180f);4->matrix.setScale(1f,-1f);5->{matrix.setRotate(90f);matrix.postScale(-1f,1f)};6->matrix.setRotate(90f);7->{matrix.setRotate(-90f);matrix.postScale(-1f,1f)};8->matrix.setRotate(-90f)};val rotated=Bitmap.createBitmap(bitmap,0,0,bitmap.width,bitmap.height,matrix,true);if(rotated!==bitmap)bitmap.recycle();bitmap=rotated}
        try{val png=ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.PNG,100,png);if(png.size()<=maximumBytes)return@withContext "data:image/png;base64,"+Base64.encodeToString(png.toByteArray(),Base64.NO_WRAP)
            if(bitmap.hasAlpha()){val paper=Bitmap.createBitmap(bitmap.width,bitmap.height,Bitmap.Config.ARGB_8888);android.graphics.Canvas(paper).apply{drawColor(android.graphics.Color.WHITE);drawBitmap(bitmap,0f,0f,null)};bitmap.recycle();bitmap=paper}
            while(bitmap.width>=80&&bitmap.height>=80){for(quality in listOf(90,80,65,50)){val out=ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.JPEG,quality,out);if(out.size()<=maximumBytes)return@withContext "data:image/jpeg;base64,"+Base64.encodeToString(out.toByteArray(),Base64.NO_WRAP)};val scaled=Bitmap.createScaledBitmap(bitmap,(bitmap.width*.8).toInt(),(bitmap.height*.8).toInt(),true);bitmap.recycle();bitmap=scaled};throw Exception("The image is too complex. Choose a smaller image.")
        }finally{bitmap.recycle()}
    }
    fun share(activity:Activity,bytes:ByteArray,name:String){val file=File(File(context.cacheDir,"exports").apply{mkdirs()},"${UUID.randomUUID()}.pdf");file.writeBytes(bytes);val uri=FileProvider.getUriForFile(context,context.packageName+".files",file,name.replace(Regex("[\\\\/:*?\"<>|]"),"_"));activity.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply{type="application/pdf";putExtra(Intent.EXTRA_STREAM,uri);putExtra(Intent.EXTRA_TITLE,name);clipData=android.content.ClipData.newRawUri(name,uri);addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)},"Share document"))}
    fun print(activity:Activity,bytes:ByteArray,name:String){(activity.getSystemService(Context.PRINT_SERVICE) as PrintManager).print(name,PdfPrinter(activity,bytes,name.replace(Regex("[\\\\/:*?\"<>|]"),"_")),PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).setColorMode(PrintAttributes.COLOR_MODE_COLOR).build())}

    companion object {
        fun b64(bytes:ByteArray)=Base64.encodeToString(bytes,Base64.NO_WRAP)
        private fun key(password:String,salt:ByteArray)=SecretKeySpec(SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(PBEKeySpec(password.toCharArray(),salt,250000,256)).encoded,"AES")
        fun encrypt(bytes:ByteArray,password:String):ByteArray{require(password.length>=12){"Use a password of at least 12 characters."};val random=SecureRandom();val salt=ByteArray(16).also(random::nextBytes);val iv=ByteArray(12).also(random::nextBytes);val cipher=Cipher.getInstance("AES/GCM/NoPadding").apply{init(Cipher.ENCRYPT_MODE,key(password,salt),GCMParameterSpec(128,iv))};return JSONObject().put("format","apex-encrypted-backup").put("version",1).put("salt",b64(salt)).put("iv",b64(iv)).put("ciphertext",b64(cipher.doFinal(bytes))).toString().toByteArray()}
        fun prepareRestore(input:ByteArray,password:String):ByteArray{var content=input;if(content.firstOrNull()?.toInt()?.and(255)!=31){val envelope=JSONObject(content.toString(Charsets.UTF_8).trimStart('\uFEFF'));if(envelope.optString("format")=="apex-encrypted-backup"){if(envelope.optInt("version")!=1)throw Exception("Unsupported encrypted backup version.");try{val salt=Base64.decode(envelope.getString("salt"),Base64.DEFAULT);val iv=Base64.decode(envelope.getString("iv"),Base64.DEFAULT);val cipher=Cipher.getInstance("AES/GCM/NoPadding").apply{init(Cipher.DECRYPT_MODE,key(password,salt),GCMParameterSpec(128,iv))};content=cipher.doFinal(Base64.decode(envelope.getString("ciphertext"),Base64.DEFAULT))}catch(e:Exception){throw Exception("The password is incorrect or the backup is damaged.")}}else{val out=ByteArrayOutputStream();GZIPOutputStream(out).use{it.write(content)};content=out.toByteArray()}}
            if(content.size>3_000_000)throw Exception("The compressed backup exceeds the 3 MB upload limit.");return content}
    }
}

private class PdfPrinter(private val context:Context,private val bytes:ByteArray,private val name:String):PrintDocumentAdapter() {
    private var attributes:PrintAttributes?=null;private val executor=Executors.newSingleThreadExecutor();private var pageCount=0
    override fun onLayout(old:PrintAttributes?,new:PrintAttributes?,signal:CancellationSignal?,callback:LayoutResultCallback?,extras:android.os.Bundle?){if(signal?.isCanceled==true){callback?.onLayoutCancelled();return};attributes=new;try{val file=File.createTempFile("print-layout-",".pdf",context.cacheDir);try{file.writeBytes(bytes);PdfRenderer(ParcelFileDescriptor.open(file,ParcelFileDescriptor.MODE_READ_ONLY)).use{pageCount=it.pageCount}}finally{file.delete()};callback?.onLayoutFinished(PrintDocumentInfo.Builder(name).setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).setPageCount(pageCount).build(),true)}catch(e:Exception){callback?.onLayoutFailed(e.message)}}
    override fun onWrite(ranges:Array<out PageRange>?,destination:ParcelFileDescriptor?,signal:CancellationSignal?,callback:WriteResultCallback?){
        executor.execute {
            val source=File.createTempFile("print-source-",".pdf",context.cacheDir)
            try {
                source.writeBytes(bytes)
                PdfRenderer(ParcelFileDescriptor.open(source,ParcelFileDescriptor.MODE_READ_ONLY)).use { renderer ->
                    val output=PrintedPdfDocument(context,attributes?:throw Exception("Printer layout is unavailable."))
                    try {
                        val written=mutableListOf<PageRange>()
                        for(index in 0 until renderer.pageCount){
                            if(ranges?.none{index in it.start..it.end}==true)continue
                            if(signal?.isCanceled==true){callback?.onWriteCancelled();return@execute}
                            renderer.openPage(index).use { page ->
                                val bitmap=Bitmap.createBitmap((page.width*2).coerceAtLeast(1),(page.height*2).coerceAtLeast(1),Bitmap.Config.ARGB_8888)
                                try {
                                    bitmap.eraseColor(android.graphics.Color.WHITE);page.render(bitmap,null,null,PdfRenderer.Page.RENDER_MODE_FOR_PRINT)
                                    val printPage=output.startPage(index);val rect=printPage.info.contentRect
                                    val scale=minOf(rect.width().toFloat()/bitmap.width,rect.height().toFloat()/bitmap.height);val width=bitmap.width*scale;val height=bitmap.height*scale
                                    printPage.canvas.drawBitmap(bitmap,null,android.graphics.RectF(rect.left+(rect.width()-width)/2,rect.top+(rect.height()-height)/2,rect.left+(rect.width()+width)/2,rect.top+(rect.height()+height)/2),null)
                                    output.finishPage(printPage);written.add(PageRange(index,index))
                                }finally{bitmap.recycle()}
                            }
                        }
                        ParcelFileDescriptor.AutoCloseOutputStream(destination?:throw Exception("Printer destination is unavailable.")).use{output.writeTo(it)}
                        callback?.onWriteFinished(written.toTypedArray())
                    }finally{output.close()}
                }
            }catch(e:Exception){callback?.onWriteFailed(e.message)}finally{source.delete()}
        }
    }
    override fun onFinish(){executor.shutdown()}
}
