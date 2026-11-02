@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package com.apexbooks.accounting

import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.compose.foundation.Image
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.apexbooks.accounting.data.s
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

private class PdfResource(val file:File):AutoCloseable {
    private val descriptor=ParcelFileDescriptor.open(file,ParcelFileDescriptor.MODE_READ_ONLY)
    private val renderer=try{PdfRenderer(descriptor)}catch(e:Exception){descriptor.close();file.delete();throw e}
    private var closed=false
    val count=renderer.pageCount
    @Synchronized fun render(index:Int):Bitmap {if(closed)throw kotlinx.coroutines.CancellationException();return renderer.openPage(index).use{page->Bitmap.createBitmap(1400,(1400f*page.height/page.width).toInt().coerceAtLeast(1),Bitmap.Config.ARGB_8888).also{it.eraseColor(android.graphics.Color.WHITE);page.render(it,null,null,PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)}}}
    @Synchronized override fun close(){if(!closed){closed=true;renderer.close();file.delete()}}
}
private class PdfOwner:AutoCloseable {
    private var resource:PdfResource?=null
    private var closed=false
    @Synchronized fun open(file:File):PdfResource {
        if(closed){file.delete();throw kotlinx.coroutines.CancellationException()}
        return PdfResource(file).also{resource=it}
    }
    @Synchronized override fun close(){closed=true;resource?.close();resource=null}
}
@Composable fun PdfScreen(vm:AppModel,activity:MainActivity,document:PdfView){var resource by remember(document.bytes){mutableStateOf<PdfResource?>(null)};var selected by remember(document.record?.s("id")){mutableStateOf("")}
    val owner=remember(document.bytes){PdfOwner()}
    DisposableEffect(owner){onDispose{owner.close()}}
    LaunchedEffect(owner){try{resource=withContext(Dispatchers.IO){val file=File.createTempFile("apex-preview-",".pdf",activity.cacheDir);try{file.writeBytes(document.bytes);owner.open(file)}catch(e:Exception){file.delete();throw e}}}catch(e:Exception){if(e !is kotlinx.coroutines.CancellationException)vm.failure(e)}}
    Dialog(onDismissRequest={vm.pdf=null},properties=DialogProperties(usePlatformDefaultWidth=false)){Surface(Modifier.fillMaxSize().safeDrawingPadding(),color=MaterialTheme.colorScheme.background){Column{TopAppBar(title={Text(document.name,maxLines=1)},navigationIcon={IconButton(onClick={vm.pdf=null}){Icon(Icons.Outlined.Close,"Close PDF")}});Row(Modifier.fillMaxWidth().padding(horizontal=12.dp),horizontalArrangement=Arrangement.spacedBy(6.dp)){TextButton(onClick={vm.files.save(document.bytes,document.name)}){Icon(Icons.Outlined.Download,null);Text("Save")};TextButton(onClick={try{vm.files.share(activity,document.bytes,document.name)}catch(e:Exception){vm.failure(e)}}){Icon(Icons.Outlined.Share,null);Text("Share")};TextButton(onClick={try{vm.files.print(activity,document.bytes,document.name)}catch(e:Exception){vm.failure(e)}}){Icon(Icons.Outlined.Print,null);Text("Print")}};Message(vm.error,true){vm.error=""};if(document.record!=null)Box(Modifier.padding(horizontal=16.dp)){Choice("Document format",selected,listOf("" to "Company default","modern" to "Modern","vintage" to "Vintage","mrp_discount" to "MRP + discount","elegant" to "Elegant","evergreen" to "Evergreen"),{selected=it;vm.documentPdf(document.record,it)})};val pdf=resource;if(pdf==null)Box(Modifier.weight(1f).fillMaxWidth(),contentAlignment=Alignment.Center){CircularProgressIndicator()}else{val pager=rememberPagerState(pageCount={pdf.count});Text("Page ${pager.currentPage+1} of ${pdf.count} · swipe to turn · pinch to zoom",Modifier.padding(14.dp),style=MaterialTheme.typography.labelMedium);HorizontalPager(pager,Modifier.weight(1f)){index->var bitmap by remember(pdf,index){mutableStateOf<Bitmap?>(null)};var scale by remember{mutableFloatStateOf(1f)};var x by remember{mutableFloatStateOf(0f)};var y by remember{mutableFloatStateOf(0f)};LaunchedEffect(pdf,index){try{bitmap=withContext(Dispatchers.IO){pdf.render(index)}}catch(e:Exception){if(e !is kotlinx.coroutines.CancellationException)vm.failure(e)}};Box(Modifier.fillMaxSize(),contentAlignment=Alignment.TopCenter){bitmap?.let{Image(it.asImageBitmap(),"Document page ${index+1}",Modifier.fillMaxWidth().padding(10.dp).graphicsLayer(scaleX=scale,scaleY=scale,translationX=x,translationY=y).pointerInput(index){detectTransformGestures{_,pan,zoom,_->scale=(scale*zoom).coerceIn(1f,4f);if(scale>1){x+=pan.x;y+=pan.y}else{x=0f;y=0f}}})}}}}}}}
}
