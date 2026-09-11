package com.trooperthorn.localmdm

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.time.Instant
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Downloads an APK and installs it silently through PackageInstaller, which a
 * Device Owner may do without a confirmation dialog. Android itself refuses an
 * update whose signing key differs from the installed package, so the optional
 * sha256 only adds transport integrity on top of that platform check.
 */
class Installer(
    private val context: Context,
    private val store: PolicyStore,
    private val onReport: () -> Unit,
) {
    private val executor = Executors.newSingleThreadExecutor()
    private val running = AtomicBoolean(false)
    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    fun start(url: String, sha256: String?): Boolean {
        if (!running.compareAndSet(false, true)) return false
        record("downloading", url, null)
        executor.execute {
            try {
                val file = download(url, sha256)
                commit(file, url)
            } catch (err: Exception) {
                Log.e(TAG, "Install failed: ${err.message}")
                record("failed", url, err.message)
                running.set(false)
            }
        }
        return true
    }

    private fun download(url: String, sha256: String?): File {
        val file = File(context.cacheDir, "update.apk")
        http.newCall(Request.Builder().url(url).build()).execute().use { response ->
            if (!response.isSuccessful) throw IllegalStateException("HTTP ${response.code} from download")
            val body = response.body ?: throw IllegalStateException("empty download body")
            file.outputStream().use { out -> body.byteStream().copyTo(out) }
        }
        if (sha256 != null) {
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { input ->
                val buffer = ByteArray(1 shl 16)
                while (true) {
                    val n = input.read(buffer)
                    if (n < 0) break
                    digest.update(buffer, 0, n)
                }
            }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            if (actual != sha256) {
                file.delete()
                throw IllegalStateException("sha256 mismatch: expected $sha256, got $actual")
            }
        }
        return file
    }

    private fun commit(file: File, url: String) {
        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setInstallReason(android.content.pm.PackageManager.INSTALL_REASON_POLICY)
        val sessionId = installer.createSession(params)
        installer.openSession(sessionId).use { session ->
            session.openWrite("update.apk", 0, file.length()).use { out ->
                file.inputStream().use { it.copyTo(out) }
                session.fsync(out)
            }
            val intent = Intent(context, InstallReceiver::class.java).setAction(InstallReceiver.ACTION)
                .putExtra(InstallReceiver.EXTRA_URL, url)
            val pending = PendingIntent.getBroadcast(
                context, sessionId, intent,
                PendingIntent.FLAG_MUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            record("installing", url, null)
            session.commit(pending.intentSender)
        }
        file.delete()
    }

    /** Called by InstallReceiver with the session result. */
    /** Lite tier: the platform is showing its confirmation dialog. */
    fun awaitingUser(url: String?) {
        record("awaiting_user", url ?: "", "confirm the install on the tablet")
        onReport()
    }

    fun finished(status: Int, message: String?, packageName: String?, url: String?) {
        val outcome = if (status == PackageInstaller.STATUS_SUCCESS) "installed" else "failed"
        record(outcome, url, message, packageName)
        running.set(false)
    }

    private fun record(state: String, url: String?, message: String?, packageName: String? = null) {
        store.lastInstall = JSONObject()
            .put("state", state)
            .put("url", url ?: JSONObject.NULL)
            .put("message", message ?: JSONObject.NULL)
            .put("package", packageName ?: JSONObject.NULL)
            .put("at", Instant.now().toString())
        onReport()
    }

    companion object {
        private const val TAG = "LocalMdm.Install"
        @Volatile var current: Installer? = null
    }

    init {
        current = this
    }
}
