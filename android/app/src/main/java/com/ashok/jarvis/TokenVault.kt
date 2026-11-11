package com.ashok.jarvis

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Stores the device token encrypted with an Android Keystore AES key. */
object TokenVault {
    private const val STORE = "jarvis_secure_preferences"
    private const val TOKEN_ENTRY = "encrypted_device_token"
    private const val BACKEND_ENTRY = "encrypted_backend_url"
    private const val DEVICE_ID_ENTRY = "encrypted_device_id"
    private const val KEY_ALIAS = "jarvis_device_token_key"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }

    private fun storeEncrypted(context: android.content.Context, entry: String, value: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val packed = cipher.iv + encrypted
        val encoded = Base64.encodeToString(packed, Base64.NO_WRAP)
        context.getSharedPreferences(STORE, android.content.Context.MODE_PRIVATE)
            .edit().putString(entry, encoded).apply()
    }

    private fun readEncrypted(context: android.content.Context, entry: String): String? {
        val encoded = context.getSharedPreferences(STORE, android.content.Context.MODE_PRIVATE)
            .getString(entry, null) ?: return null
        val packed = Base64.decode(encoded, Base64.NO_WRAP)
        require(packed.size > 12) { "Stored token data is invalid" }
        val iv = packed.copyOfRange(0, 12)
        val ciphertext = packed.copyOfRange(12, packed.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        return cipher.doFinal(ciphertext).toString(Charsets.UTF_8)
    }

    fun store(context: android.content.Context, token: String) =
        storeEncrypted(context, TOKEN_ENTRY, token)

    fun read(context: android.content.Context): String? = readEncrypted(context, TOKEN_ENTRY)

    fun storeBackendUrl(context: android.content.Context, backendUrl: String) =
        storeEncrypted(context, BACKEND_ENTRY, backendUrl)

    fun readBackendUrl(context: android.content.Context): String? =
        readEncrypted(context, BACKEND_ENTRY)

    fun storeDeviceId(context: android.content.Context, deviceId: String) =
        storeEncrypted(context, DEVICE_ID_ENTRY, deviceId)

    fun readDeviceId(context: android.content.Context): String? =
        readEncrypted(context, DEVICE_ID_ENTRY)

    fun clearDeviceId(context: android.content.Context) {
        context.getSharedPreferences(STORE, android.content.Context.MODE_PRIVATE)
            .edit().remove(DEVICE_ID_ENTRY).apply()
    }

    fun clear(context: android.content.Context) {
        context.getSharedPreferences(STORE, android.content.Context.MODE_PRIVATE)
            .edit().remove(TOKEN_ENTRY).remove(BACKEND_ENTRY).remove(DEVICE_ID_ENTRY).apply()
    }
}
