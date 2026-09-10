package com.trooperthorn.localmdm

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/**
 * Lock task mode must be entered by an activity in an allow-listed package,
 * so this activity starts it and then hands off to the target application.
 * A second launch with EXTRA_STOP leaves lock task mode and finishes.
 */
class KioskActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handle(intent)
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
        packageManager.getLaunchIntentForPackage(target)?.let { launch ->
            startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }

    companion object {
        const val EXTRA_TARGET = "target"
        const val EXTRA_STOP = "stop"
    }
}
