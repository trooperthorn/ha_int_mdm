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
 */
class KioskActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private var pending: Runnable? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_kiosk)
        handle(intent)
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
            runCatching { stopLockTask() }
            MdmService.requestReport(this)
            finishAndRemoveTask()
            return
        }
        // No extras means a HOME press or a boot into the persistent home:
        // follow the stored policy instead of an explicit request.
        val target = intent.getStringExtra(EXTRA_TARGET)
            ?: PolicyStore(this).policy.takeIf { it.kioskMode }?.kioskPackages?.firstOrNull()
            ?: return finish()
        runCatching { startLockTask() }
        MdmService.requestReport(this)
        pending?.let(handler::removeCallbacks)
        val launch = Runnable {
            pending = null
            packageManager.getLaunchIntentForPackage(target)?.let { intent ->
                startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
        }
        pending = launch
        handler.postDelayed(launch, SPLASH_MS)
    }

    companion object {
        const val EXTRA_TARGET = "target"
        const val EXTRA_STOP = "stop"
        const val SPLASH_MS = 2000L
    }
}
