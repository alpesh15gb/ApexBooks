package com.apexbooks.accounting.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Session tokens are encrypted with a non-exportable Android Keystore key. */
class SessionVault(context: Context) {
    private val preferences = context.getSharedPreferences("apex_sessions", Context.MODE_PRIVATE)
    private val alias = "ApexBooks.Session.v1"
    private fun name(origin: String) = MessageDigest.getInstance("SHA-256").digest(origin.toByteArray()).joinToString("") { "%02x".format(it) }
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build())
        }.generateKey()
    }
    fun protect(bytes: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key()); return cipher.iv + cipher.doFinal(bytes)
    }
    fun unprotect(bytes: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12))); return cipher.doFinal(bytes.copyOfRange(12, bytes.size))
    }
    fun save(origin: String, session: JSONObject) { preferences.edit().putString(name(origin), Base64.encodeToString(protect(session.toString().toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)).apply() }
    fun load(origin: String): JSONObject? = runCatching { preferences.getString(name(origin), null)?.let { JSONObject(unprotect(Base64.decode(it, Base64.NO_WRAP)).toString(Charsets.UTF_8)) } }.getOrElse { clear(origin); null }
    fun clear(origin: String) { preferences.edit().remove(name(origin)).apply() }
}
