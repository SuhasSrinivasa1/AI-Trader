package com.multify.autotrader.ui.theme
import android.app.Activity
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val Scheme=darkColorScheme(
 primary=Color(0xFF39D7C5),onPrimary=Color(0xFF00201C),primaryContainer=Color(0xFF113B3B),onPrimaryContainer=Color(0xFFB9FFF5),
 secondary=Color(0xFFFFC857),onSecondary=Color(0xFF2A1A00),error=Color(0xFFFF6B7A),
 background=Color(0xFF07111F),onBackground=Color(0xFFF3F7FB),surface=Color(0xFF0E1A2B),onSurface=Color(0xFFF3F7FB),
 surfaceVariant=Color(0xFF17253A),onSurfaceVariant=Color(0xFFAAB7C7),outline=Color(0xFF3A4B61)
)
@Composable
fun MultifyTheme(content: @Composable () -> Unit){
 val view=LocalView.current
 if(!view.isInEditMode){
  val window=(view.context as Activity).window
  WindowCompat.getInsetsController(window,view).apply{
   isAppearanceLightStatusBars=false
   isAppearanceLightNavigationBars=false
  }
 }
 MaterialTheme(colorScheme=Scheme,content=content)
}
