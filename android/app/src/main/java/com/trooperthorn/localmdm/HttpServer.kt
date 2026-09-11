package com.trooperthorn.localmdm

import android.os.Handler
import android.os.Looper
import android.util.Log
import fi.iki.elonen.NanoHTTPD
import org.json.JSONException
import org.json.JSONObject
import java.security.MessageDigest

/**
 * The control-plane endpoint Home Assistant talks to. Plain HTTP on the LAN,
 * bearer token on every request; docs/security.md explains the trust model.
 */
class HttpServer(
    port: Int,
    private val store: PolicyStore,
    private val engine: PolicyEngine,
    private val onReport: () -> Unit,
    private val installer: Installer,
) : NanoHTTPD(port) {

    override fun serve(session: IHTTPSession): Response {
        if (!authorized(session)) return text(Response.Status.UNAUTHORIZED, "unauthorized")
        val path = session.uri.removeSuffix("/")
        return try {
            when {
                path == "/v1/status" && session.method == Method.GET -> json(engine.status())
                path == "/v1/policy" && session.method == Method.PUT -> putPolicy(session)
                path == "/v1/webhook" && session.method == Method.PUT -> putWebhook(session)
                path == "/v1/actions/lock_screen" && session.method == Method.POST -> lock()
                path == "/v1/actions/install_package" && session.method == Method.POST -> install(session)
                path == "/v1/actions/configure_wifi" && session.method == Method.POST -> configureWifi(session)
                path == "/v1/actions/reboot" && session.method == Method.POST -> reboot()
                else -> text(Response.Status.NOT_FOUND, "not found")
            }
        } catch (err: JSONException) {
            text(Response.Status.BAD_REQUEST, "malformed JSON: ${err.message}")
        }
    }

    private fun authorized(session: IHTTPSession): Boolean {
        val header = session.headers["authorization"] ?: return false
        val presented = header.removePrefix("Bearer ").trim()
        return constantTimeEquals(presented, store.token)
    }

    private fun putPolicy(session: IHTTPSession): Response {
        val body = readJson(session)
        val version = body.optInt("version", store.policyVersion + 1)
        val policy = try {
            Policy.fromJson(body.getJSONObject("policy"), "com.trooperthorn.localmdm")
        } catch (err: Policy.Companion.UnsafePolicy) {
            Log.w(TAG, "Refused unsafe policy: ${err.message}")
            return text(UNPROCESSABLE_ENTITY, err.message ?: "unsafe policy")
        } catch (err: Policy.Companion.InvalidPolicy) {
            return text(Response.Status.BAD_REQUEST, err.message ?: "invalid policy")
        }
        if (!engine.isDeviceOwner) {
            return text(UNPROCESSABLE_ENTITY, "not device owner")
        }
        engine.apply(policy, version)
        onReport()
        return json(engine.status())
    }

    private fun putWebhook(session: IHTTPSession): Response {
        val url = readJson(session).optString("url", "")
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            return text(Response.Status.BAD_REQUEST, "url must be http or https")
        }
        store.webhookUrl = url
        onReport()
        return json(JSONObject().put("ok", true))
    }

    /**
     * The response must leave before dpm.reboot() tears the socket down, or
     * Home Assistant reports a failure for a reboot that happened (seen on
     * 2026-09-11). The reboot itself runs from the main looper after a short
     * delay so this handler can finish writing.
     */
    private fun reboot(): Response {
        if (!engine.isDeviceOwner) return text(UNPROCESSABLE_ENTITY, "not device owner")
        Handler(Looper.getMainLooper()).postDelayed({ engine.reboot() }, REBOOT_DELAY_MS)
        return json(JSONObject().put("ok", true).put("delay_ms", REBOOT_DELAY_MS))
    }

    private fun lock(): Response =
        if (engine.lockNow()) json(JSONObject().put("ok", true))
        else text(UNPROCESSABLE_ENTITY, "lockNow refused")

    private fun install(session: IHTTPSession): Response {
        val body = readJson(session)
        val url = body.optString("url", "")
        val sha256 = body.optString("sha256", "").lowercase().removePrefix("sha256:")
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            return text(Response.Status.BAD_REQUEST, "url must be http or https")
        }
        if (sha256.isNotEmpty() && !sha256.matches(Regex("[0-9a-f]{64}"))) {
            return text(Response.Status.BAD_REQUEST, "sha256 must be 64 hex characters")
        }
        if (!engine.isDeviceOwner) return text(UNPROCESSABLE_ENTITY, "not device owner")
        if (!installer.start(url, sha256.ifEmpty { null })) {
            return text(UNPROCESSABLE_ENTITY, "an install is already running")
        }
        return newFixedLengthResponse(ACCEPTED, "application/json", JSONObject().put("ok", true).toString())
    }

    private fun configureWifi(session: IHTTPSession): Response {
        val body = readJson(session)
        val ssid = body.optString("ssid", "")
        if (ssid.isEmpty() || ssid.length > 32) return text(Response.Status.BAD_REQUEST, "ssid must be 1 to 32 characters")
        val password = body.optString("password", "").ifEmpty { null }
        if (password != null && password.length !in 8..63) {
            return text(Response.Status.BAD_REQUEST, "password must be 8 to 63 characters")
        }
        if (!engine.isDeviceOwner) return text(UNPROCESSABLE_ENTITY, "not device owner")
        return try {
            val id = engine.wifiControl.configure(ssid, password, body.optBoolean("hidden", false))
            onReport()
            json(JSONObject().put("ok", true).put("network_id", id))
        } catch (err: RuntimeException) {
            Log.e(TAG, "configure_wifi failed: ${err.message}")
            text(UNPROCESSABLE_ENTITY, err.message ?: "configure_wifi failed")
        }
    }

    private object ACCEPTED : Response.IStatus {
        override fun getRequestStatus(): Int = 202
        override fun getDescription(): String = "202 Accepted"
    }

    private fun readJson(session: IHTTPSession): JSONObject {
        val length = session.headers["content-length"]?.toIntOrNull() ?: 0
        if (length > MAX_BODY) throw JSONException("body too large")
        val buffer = ByteArray(length)
        var read = 0
        while (read < length) {
            val n = session.inputStream.read(buffer, read, length - read)
            if (n < 0) break
            read += n
        }
        return JSONObject(String(buffer, 0, read, Charsets.UTF_8))
    }

    private object UNPROCESSABLE_ENTITY : Response.IStatus {
        override fun getRequestStatus(): Int = 422
        override fun getDescription(): String = "422 Unprocessable Entity"
    }

    private fun json(body: JSONObject): Response =
        newFixedLengthResponse(Response.Status.OK, "application/json", body.toString())

    private fun text(status: Response.IStatus, body: String): Response =
        newFixedLengthResponse(status, "text/plain", body)

    private fun constantTimeEquals(a: String, b: String): Boolean {
        val da = MessageDigest.getInstance("SHA-256").digest(a.toByteArray())
        val db = MessageDigest.getInstance("SHA-256").digest(b.toByteArray())
        return MessageDigest.isEqual(da, db)
    }

    companion object {
        const val REBOOT_DELAY_MS = 500L
        private const val TAG = "LocalMdm.Http"
        private const val MAX_BODY = 64 * 1024
    }
}
