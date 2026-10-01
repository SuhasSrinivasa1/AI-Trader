package com.multify.autotrader
import android.Manifest
import android.app.NotificationManager
import android.content.ComponentName
import android.content.pm.PackageManager
import android.os.*
import androidx.activity.*
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import com.multify.autotrader.service.MultifyNotificationListenerService
import com.multify.autotrader.ui.MultifyApp
import com.multify.autotrader.ui.theme.MultifyTheme

class MainActivity:ComponentActivity(){
 private var notificationAccess by mutableStateOf(false)
 override fun onCreate(savedInstanceState:Bundle?){installSplashScreen();super.onCreate(savedInstanceState);enableEdgeToEdge();requestNotifications();refreshAccess()
  val app=application as MultifyApplication
  setContent{MultifyTheme{MultifyApp(app.container,notificationAccess,::refreshAccess)}}
 }
 override fun onResume(){super.onResume();refreshAccess()}
 private fun refreshAccess(){val m=getSystemService(NotificationManager::class.java);notificationAccess=m.isNotificationListenerAccessGranted(ComponentName(this,MultifyNotificationListenerService::class.java))}
 private fun requestNotifications(){if(Build.VERSION.SDK_INT>=33&&ContextCompat.checkSelfPermission(this,Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)ActivityCompat.requestPermissions(this,arrayOf(Manifest.permission.POST_NOTIFICATIONS),1001)}
}
