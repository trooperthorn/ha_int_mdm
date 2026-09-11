package com.trooperthorn.localmdm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller

/** Receives the PackageInstaller session result and hands it to the Installer. */
class InstallReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            // Only reached without Device Owner (lite tier): Android wants the
            // user to confirm. Show the dialog and report that it is waiting;
            // the final status arrives through this receiver afterwards.
            @Suppress("DEPRECATION")
            val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
            if (confirm != null) {
                context.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                Installer.current?.awaitingUser(intent.getStringExtra(EXTRA_URL))
            } else {
                Installer.current?.finished(PackageInstaller.STATUS_FAILURE, "user action required", null, intent.getStringExtra(EXTRA_URL))
            }
            return
        }
        Installer.current?.finished(
            status,
            intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE),
            intent.getStringExtra(PackageInstaller.EXTRA_PACKAGE_NAME),
            intent.getStringExtra(EXTRA_URL),
        )
    }

    companion object {
        const val ACTION = "com.trooperthorn.localmdm.INSTALL_RESULT"
        const val EXTRA_URL = "url"
    }
}
