package com.trooperthorn.localmdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter

/**
 * Post-install approval. PACKAGE_ADDED is not on Android's implicit-broadcast
 * exemption list, so it is registered here by the foreground service rather
 * than in the manifest. A fresh install (not an update) under the allowlist is
 * suspended immediately and reported as pending; adding it to
 * allowed_packages from Home Assistant is the approval.
 */
class PackageWatch(private val context: Context, private val engine: PolicyEngine, private val onChange: () -> Unit) {
    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context, intent: Intent) {
            val pkg = intent.data?.schemeSpecificPart ?: return
            when (intent.action) {
                Intent.ACTION_PACKAGE_ADDED -> {
                    if (intent.getBooleanExtra(Intent.EXTRA_REPLACING, false)) return
                    engine.onPackageAdded(pkg)
                }
                Intent.ACTION_PACKAGE_FULLY_REMOVED -> engine.onPackageRemoved(pkg)
                else -> return
            }
            onChange()
        }
    }

    fun start() {
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_PACKAGE_ADDED)
            addAction(Intent.ACTION_PACKAGE_FULLY_REMOVED)
            addDataScheme("package")
        }
        context.registerReceiver(receiver, filter)
    }

    fun stop() {
        runCatching { context.unregisterReceiver(receiver) }
    }
}
