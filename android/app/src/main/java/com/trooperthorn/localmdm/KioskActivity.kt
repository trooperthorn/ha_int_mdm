package com.trooperthorn.localmdm

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper

/**
 * Lock task mode must be entered by an activity in an allow-listed package,
 * so this activity starts it and then hands off to the target application.
 * A second launch with EXTRA_STOP leaves lock task mode and finishes.
 *
 * Before the hand-off it shows a lock splash for SPLASH_MS so the tablet
 * visibly reads as MDM-managed at boot and whenever kiosk re-asserts. This is
 * the DPC's own window: no boot animation, no Knox, nothing vendor-specific.
 *
 * The hand-off runs from onResume, not only from the launching intent, so
 * coming back to the splash (Back out of the kiosk app on the lite tier,
 * where nothing pins the app's task) hands off again instead of parking on
 * the splash (seen on a Fire, 2026-09-11).
 */
class KioskActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private var pending: Runnable? = null
    private var target: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_kiosk)
        handle(intent)
    }

    override fun onResume() {
        super.onResume()
        val pkg = target ?: return
        if (pending != null) return
        val launch = Runnable {
            pending = null
            packageManager.getLaunchIntentForPackage(pkg)?.let { intent ->
                startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
        }
        pending = launch
        handler.postDelayed(launch, SPLASH_MS)
    }

    override fun onPause() {
        // A hand-off that has not fired yet is dropped; onResume schedules a
        // fresh one when the splash is next in front.
        pending?.let(handler::removeCallbacks)
        pending = null
        super.onPause()
    }

    override fun onDestroy() {
        pending?.let(handler::removeCallbacks)
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    private fun handle(intent: Intent) {
        if (intent.getBooleanExtra(EXTRA_STOP, false)) {
            target = null
            runCatching { stopLockTask() }
            MdmService.requestReport(this)
            finishAndRemoveTask()
            return
        }
        // No extras means a HOME press or a boot into the persistent home:
        // follow the stored policy instead of an explicit request.
        target = intent.getStringExtra(EXTRA_TARGET)
            ?: PolicyStore(this).policy.takeIf { it.kioskMode }?.kioskPackages?.firstOrNull()
            ?: return finish()
        // Only a Device Owner has this package allow-listed, so only then does
        // startLockTask enter lock task. Without ownership the same call falls
        // back to screen pinning, which pins this splash instead of the kiosk
        // app and traps the tablet on it (Fire, 2026-09-11).
        val dpm = getSystemService(DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
        if (dpm.isLockTaskPermitted(packageName)) runCatching { startLockTask() }
        MdmService.requestReport(this)
    }

    companion object {
        const val EXTRA_TARGET = "target"
        const val EXTRA_STOP = "stop"
        const val SPLASH_MS = 2000L
    }
}
