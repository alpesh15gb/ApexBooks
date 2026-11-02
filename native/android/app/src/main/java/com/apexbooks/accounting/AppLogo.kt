package com.apexbooks.accounting

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp

@Composable fun AppLogo(modifier:Modifier=Modifier){
    Surface(modifier,color=Color.White,shape=RoundedCornerShape(7.dp)){
        Image(painterResource(R.drawable.apexbooks_wordmark),"Apex Books — Your books in balance",Modifier.padding(10.dp).fillMaxWidth().aspectRatio(1569f/230f),contentScale=ContentScale.Fit)
    }
}
