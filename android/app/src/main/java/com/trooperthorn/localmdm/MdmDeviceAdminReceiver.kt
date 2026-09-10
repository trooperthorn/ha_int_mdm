package com.trooperthorn.localmdm

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent

class MdmDeviceAdminReceiver : DeviceAdminReceiver() {
    override fun onEnabled(context: Context, intent: Intent) {
        MdmService.start(context)
    }

    override fun onProfileProvisioningComplete(context: Context, intent: Intent) {
        MdmService.start(context)
    }
}
