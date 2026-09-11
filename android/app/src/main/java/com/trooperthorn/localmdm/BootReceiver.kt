package com.trooperthorn.localmdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Brings the service back after a boot and after the DPC updates itself. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED -> MdmService.start(context)
        }
    }
}
