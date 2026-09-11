package com.trooperthorn.localmdm

import android.Manifest
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.util.Log

/**
 * Wi-Fi provisioning for a Device Owner. The network is handed to Android's
 * own configured-network store; the DPC keeps no copy of the password. The
 * user's Wi-Fi settings are never restricted (docs/security.md), so a wrong
 * password from the control plane cannot strand the tablet.
 */
class Wifi(private val context: Context) {
    private val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    private val admin = ComponentName(context, MdmDeviceAdminReceiver::class.java)

    /**
     * Reading the connected SSID needs the fine location permission and the
     * device location toggle; a Device Owner may set both for itself.
     */
    fun grantLocationToSelf() {
        runCatching {
            dpm.setPermissionGrantState(
                admin, context.packageName, Manifest.permission.ACCESS_FINE_LOCATION,
                DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED,
            )
        }
        runCatching { dpm.setLocationEnabled(admin, true) }
    }

    fun isEnabled(): Boolean = wifi.isWifiEnabled

    fun ensureEnabled(): Boolean {
        if (wifi.isWifiEnabled) return true
        @Suppress("DEPRECATION")
        return wifi.setWifiEnabled(true)
    }

    /** Adds (or updates) a WPA2/WPA3 personal network and asks Android to join it. */
    fun configure(ssid: String, password: String?, hidden: Boolean): Int {
        @Suppress("DEPRECATION")
        val config = WifiConfiguration().apply {
            SSID = "\"$ssid\""
            hiddenSSID = hidden
            if (password.isNullOrEmpty()) {
                setSecurityParams(WifiConfiguration.SECURITY_TYPE_OPEN)
            } else {
                preSharedKey = "\"$password\""
                setSecurityParams(WifiConfiguration.SECURITY_TYPE_PSK)
            }
        }
        ensureEnabled()
        val result = wifi.addNetworkPrivileged(config)
        if (result.statusCode != WifiManager.AddNetworkResult.STATUS_SUCCESS) {
            throw IllegalStateException("addNetworkPrivileged status ${result.statusCode}")
        }
        // disableOthers must stay false: true drops the current connection to
        // try the new network, which took a Galaxy Tab off the LAN for several
        // seconds on 2026-09-11. Android joins the new network on its own when
        // the current one is gone.
        @Suppress("DEPRECATION")
        wifi.enableNetwork(result.networkId, false)
        Log.i(TAG, "Configured network id ${result.networkId}")
        return result.networkId
    }

    fun connectedSsid(): String? {
        @Suppress("DEPRECATION")
        val raw = runCatching { wifi.connectionInfo.ssid }.getOrNull() ?: return null
        if (raw == WifiManager.UNKNOWN_SSID || raw.isEmpty()) return null
        return raw.removeSurrounding("\"")
    }

    companion object {
        private const val TAG = "LocalMdm.Wifi"
    }
}
