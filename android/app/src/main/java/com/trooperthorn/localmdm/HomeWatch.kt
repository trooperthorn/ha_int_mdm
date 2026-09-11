package com.trooperthorn.localmdm

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.Process
import android.util.Log

/**
 * Lite-tier kiosk helper. A Device Owner keeps the kiosk app in front with
 * lock task and a persistent HOME activity; without ownership neither is
 * available (Fire OS forces its own launcher, marks it protected, and does
 * not deliver its window events to third-party accessibility services). So
 * while kiosk is on this polls the usage-events log once a second and, when
 * a launcher has just come to the foreground, sends the kiosk target back.
 *
 * Needs the GET_USAGE_STATS app op, granted once over adb by
 * scripts/provision_lite.sh. Reads only package names and timestamps.
 */
class HomeWatch(private val context: Context, private val store: PolicyStore) {
    private val handler = Handler(Looper.getMainLooper())
    private val usage = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
    private var lastSeen = System.currentTimeMillis()
    private var lastRedirect = 0L
    private var running = false

    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            runCatching { check() }.onFailure { Log.w(TAG, "usage check failed: ${it.message}") }
            handler.postDelayed(this, PERIOD_MS)
        }
    }

    val granted: Boolean
        get() {
            val ops = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
            @Suppress("DEPRECATION")
            val mode = ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), context.packageName)
            return mode == AppOpsManager.MODE_ALLOWED
        }

    fun start() {
        if (running) return
        running = true
        lastSeen = System.currentTimeMillis()
        handler.post(tick)
    }

    fun stop() {
        running = false
        handler.removeCallbacks(tick)
    }

    private fun check() {
        val policy = store.policy
        if (!policy.kioskMode) return
        val target = policy.kioskPackages.firstOrNull() ?: return
        val now = System.currentTimeMillis()
        val events = usage.queryEvents(lastSeen - 1, now)
        lastSeen = now
        var launcherUp = false
        val event = UsageEvents.Event()
        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            if (event.eventType != UsageEvents.Event.MOVE_TO_FOREGROUND) continue
            val pkg = event.packageName
            launcherUp = pkg != target && pkg != context.packageName && isLauncher(pkg)
        }
        if (!launcherUp || now - lastRedirect < DEBOUNCE_MS) return
        lastRedirect = now
        Log.i(TAG, "Launcher in front while kiosk is on; returning to $target")
        context.startActivity(
            Intent(context, KioskActivity::class.java)
                .putExtra(KioskActivity.EXTRA_TARGET, target)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    }

    /** Any package that resolves the HOME intent, so there is no launcher list to maintain. */
    private fun isLauncher(pkg: String): Boolean {
        val home = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
        return context.packageManager.queryIntentActivities(home, 0).any { it.activityInfo.packageName == pkg }
    }

    companion object {
        private const val TAG = "LocalMdm.HomeWatch"
        private const val PERIOD_MS = 1000L
        private const val DEBOUNCE_MS = 1500L
    }
}
