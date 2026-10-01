package com.multify.autotrader.ui.components
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import java.text.NumberFormat
import java.util.Locale

@Composable fun StatusPill(text:String,positive:Boolean?=null){
 val bg=when(positive){true->MaterialTheme.colorScheme.primaryContainer;false->MaterialTheme.colorScheme.error.copy(alpha=.18f);null->MaterialTheme.colorScheme.surfaceVariant}
 val fg=when(positive){true->MaterialTheme.colorScheme.primary;false->MaterialTheme.colorScheme.error;null->MaterialTheme.colorScheme.onSurfaceVariant}
 Surface(shape=RoundedCornerShape(999.dp),color=bg){Text(text,color=fg,style=MaterialTheme.typography.labelMedium,modifier=Modifier.padding(horizontal=10.dp,vertical=6.dp))}
}
@Composable fun MetricCard(label:String,value:String,supporting:String,icon:ImageVector,accent:Color=MaterialTheme.colorScheme.primary,modifier:Modifier=Modifier){
 ElevatedCard(modifier=modifier,shape=RoundedCornerShape(20.dp),colors=CardDefaults.elevatedCardColors(containerColor=MaterialTheme.colorScheme.surface)){
  Column(Modifier.padding(18.dp)){Box(Modifier.size(38.dp).background(accent.copy(alpha=.14f),RoundedCornerShape(12.dp)),contentAlignment=Alignment.Center){Icon(icon,null,tint=accent,modifier=Modifier.size(20.dp))}
   Spacer(Modifier.height(14.dp));Text(label,style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(value,style=MaterialTheme.typography.headlineSmall,fontWeight=FontWeight.SemiBold);Text(supporting,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}
 }
}
@Composable fun Banner(title:String,message:String,ok:Boolean,action:String?=null,onAction:(()->Unit)?=null){
 Card(shape=RoundedCornerShape(18.dp),colors=CardDefaults.cardColors(containerColor=if(ok)MaterialTheme.colorScheme.primaryContainer.copy(alpha=.65f) else MaterialTheme.colorScheme.error.copy(alpha=.12f))){
  Row(Modifier.fillMaxWidth().padding(16.dp),verticalAlignment=Alignment.CenterVertically){Icon(if(ok)Icons.Default.Verified else Icons.Default.Warning,null,tint=if(ok)MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error);Spacer(Modifier.width(12.dp));Column(Modifier.weight(1f)){Text(title,fontWeight=FontWeight.SemiBold);Text(message,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)};if(action!=null&&onAction!=null)TextButton(onClick=onAction){Text(action)}}
 }
}
@Composable fun EventRow(symbol:String?,type:String,time:String,action:String?,reason:String?,status:String){
 Row(Modifier.fillMaxWidth().padding(vertical=10.dp),verticalAlignment=Alignment.Top){Box(Modifier.size(42.dp).background(MaterialTheme.colorScheme.surfaceVariant,RoundedCornerShape(13.dp)),contentAlignment=Alignment.Center){Icon(when(type){"BOOK_PROFIT"->Icons.Default.TaskAlt;"AUTO_PAUSED"->Icons.Default.PauseCircle;"PRE_ALERT"->Icons.Default.NotificationsActive;else->Icons.Default.NorthEast},null,tint=MaterialTheme.colorScheme.primary)};Spacer(Modifier.width(12.dp));Column(Modifier.weight(1f)){Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(symbol?:type.replace('_',' '),fontWeight=FontWeight.SemiBold);Text(time,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)};Text(action?:type.replace('_',' '),style=MaterialTheme.typography.bodySmall,maxLines=1,overflow=TextOverflow.Ellipsis);if(!reason.isNullOrBlank())Text(reason,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=2,overflow=TextOverflow.Ellipsis)};Spacer(Modifier.width(8.dp));StatusPill(status,when(status){"SENT"->true;"FAILED"->false;else->null})}
}
fun inr(v:Double):String=NumberFormat.getCurrencyInstance(Locale("en","IN")).format(v)
