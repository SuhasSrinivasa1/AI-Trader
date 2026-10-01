package com.multify.autotrader.data.repository
import android.content.Context
import android.security.keystore.*
import android.util.Base64
import java.security.KeyStore
import javax.crypto.*
import javax.crypto.spec.GCMParameterSpec

class SecretStore(context:Context){
 private val prefs=context.getSharedPreferences("multify_secure",Context.MODE_PRIVATE)
 private val alias="multify.device.secret.v1"
 private val ks=KeyStore.getInstance("AndroidKeyStore").apply{load(null)}
 private fun key():SecretKey{
  val old=ks.getKey(alias,null) as? SecretKey
  if(old!=null)return old
  val g=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore")
  g.init(KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
   .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build())
  return g.generateKey()
 }
 fun putDeviceSecret(secret:String){
  if(secret.isBlank()){prefs.edit().clear().apply();return}
  val c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,key())
  val enc=c.doFinal(secret.toByteArray())
  prefs.edit().putString("ciphertext",Base64.encodeToString(enc,Base64.NO_WRAP)).putString("iv",Base64.encodeToString(c.iv,Base64.NO_WRAP)).apply()
 }
 fun getDeviceSecret():String?{
  val ct=prefs.getString("ciphertext",null)?:return null;val iv=prefs.getString("iv",null)?:return null
  return runCatching{val c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,Base64.decode(iv,Base64.NO_WRAP)));String(c.doFinal(Base64.decode(ct,Base64.NO_WRAP)))}.getOrNull()
 }
 fun hasDeviceSecret()=!getDeviceSecret().isNullOrBlank()
}
