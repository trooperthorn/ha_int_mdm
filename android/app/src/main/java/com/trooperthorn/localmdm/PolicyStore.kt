package com.trooperthorn.localmdm

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONObject
import java.security.SecureRandom
import java.util.UUID

/** Persists the applied policy, its version, the pairing token, and the webhook URL. */
class PolicyStore(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("local_mdm", Context.MODE_PRIVATE)
    private val selfPackage = context.packageName

    val deviceId: String
        get() = prefs.getString(KEY_DEVICE_ID, null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString(KEY_DEVICE_ID, it).apply()
        }

    var token: String
        get() = prefs.getString(KEY_TOKEN, null) ?: rotateToken()
        private set(value) = prefs.edit().putString(KEY_TOKEN, value).apply()

    fun rotateToken(): String {
        val bytes = ByteArray(24)
        SecureRandom().nextBytes(bytes)
        val value = bytes.joinToString("") { "%02x".format(it) }
        token = value
        return value
    }

    var webhookUrl: String?
        get() = prefs.getString(KEY_WEBHOOK, null)
        set(value) = prefs.edit().putString(KEY_WEBHOOK, value).apply()

    var policyVersion: Int
        get() = prefs.getInt(KEY_VERSION, 0)
        set(value) = prefs.edit().putInt(KEY_VERSION, value).apply()

    var policy: Policy
        get() {
            val raw = prefs.getString(KEY_POLICY, null) ?: return Policy()
            return runCatching { Policy.fromJson(JSONObject(raw), selfPackage) }.getOrDefault(Policy())
        }
        set(value) = prefs.edit().putString(KEY_POLICY, value.toJson().toString()).apply()

    /** Per-key enforcement outcome from the last apply: applied, failed, or refused. */
    var enforcement: Map<String, String>
        get() {
            val raw = prefs.getString(KEY_ENFORCEMENT, null) ?: return emptyMap()
            val json = JSONObject(raw)
            return json.keys().asSequence().associateWith { json.getString(it) }
        }
        set(value) = prefs.edit().putString(KEY_ENFORCEMENT, JSONObject(value).toString()).apply()

    /** Outcome of the last install_package action, reported until the next one. */
    var lastInstall: JSONObject?
        get() = prefs.getString(KEY_LAST_INSTALL, null)?.let { runCatching { JSONObject(it) }.getOrNull() }
        set(value) = prefs.edit().putString(KEY_LAST_INSTALL, value?.toString()).apply()

    companion object {
        private const val KEY_LAST_INSTALL = "last_install"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_TOKEN = "token"
        private const val KEY_WEBHOOK = "webhook_url"
        private const val KEY_VERSION = "policy_version"
        private const val KEY_POLICY = "policy"
        private const val KEY_ENFORCEMENT = "enforcement"
    }
}
