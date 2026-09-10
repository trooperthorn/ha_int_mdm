package com.trooperthorn.localmdm

import android.util.Log
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** POSTs the status document to Home Assistant's webhook, off the main thread. */
class WebhookReporter(private val store: PolicyStore, private val engine: PolicyEngine) {
    private val executor = Executors.newSingleThreadExecutor()
    private val http = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .writeTimeout(3, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.SECONDS)
        .build()

    fun report() {
        val url = store.webhookUrl ?: return
        executor.execute {
            val body = engine.status().toString().toRequestBody(JSON)
            val request = Request.Builder().url(url).post(body).build()
            try {
                http.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        Log.w(TAG, "Home Assistant answered ${response.code} to the report")
                    }
                }
            } catch (err: java.io.IOException) {
                Log.w(TAG, "Report to Home Assistant failed: ${err.message}")
            }
        }
    }

    companion object {
        private const val TAG = "LocalMdm.Webhook"
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }
}
