package com.trooperthorn.localmdm

import android.Manifest
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.os.Build
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
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            runCatching { dpm.setLocationEnabled(admin, true) }
        }
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
        val networkId = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val result = wifi.addNetworkPrivileged(config)
            if (result.statusCode != WifiManager.AddNetworkResult.STATUS_SUCCESS) {
                throw IllegalStateException("addNetworkPrivileged status ${result.statusCode}")
            }
            result.networkId
        } else {
            // Android 9/10 (Fire OS 7): the pre-S path, still honoured for a
            // Device Owner, which owns the configured-network store.
            @Suppress("DEPRECATION")
            val id = wifi.addNetwork(config)
            if (id < 0) throw IllegalStateException("addNetwork returned $id")
            id
        }
        // disableOthers must stay false: true drops the current connection to
        // try the new network, which took a Galaxy Tab off the LAN for several
        // seconds on 2026-09-11. Android joins the new network on its own when
        // the current one is gone.
        @Suppress("DEPRECATION")
        wifi.enableNetwork(networkId, false)
        Log.i(TAG, "Configured network id $networkId")
        return networkId
    }

    @Volatile private var lastSsid: String? = null

    /**
     * One UI answers the deprecated connectionInfo call with the SSID only
     * some of the time even with location granted and on, so the last good
     * value is kept while Wi-Fi stays connected and dropped when it is not.
     */
    /**
     * MAC address in use on the current connection, the one the access point
     * and the UniFi controller see (randomised per network on Android 10+).
     * Only a Device Owner gets the real value; anyone else gets the
     * 02:00:00:00:00:00 placeholder, which is dropped.
     */
    @Suppress("DEPRECATION")
    fun macInUse(): String? {
        // Android 16 (Pixel Tablet, 2026-09-11) returned the placeholder on
        // both paths even for a Device Owner, so this is usually null there;
        // kept because earlier releases honour the owner exemption.
        val fromTransport = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            runCatching {
                val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as android.net.ConnectivityManager
                (cm.getNetworkCapabilities(cm.activeNetwork)?.transportInfo as? android.net.wifi.WifiInfo)?.macAddress
            }.getOrNull()
        } else null
        val fromLegacy = runCatching { wifi.connectionInfo?.macAddress }.getOrNull()
        return listOfNotNull(fromTransport, fromLegacy)
            .firstOrNull { it.isNotEmpty() && it != PLACEHOLDER_MAC }
            ?.lowercase()
    }

    fun connectedSsid(): String? {
        if (!Network.isWifiConnected(context)) {
            lastSsid = null
            return null
        }
        @Suppress("DEPRECATION")
        val raw = runCatching { wifi.connectionInfo.ssid }.getOrNull()
        val fresh = raw?.takeUnless { it == WifiManager.UNKNOWN_SSID || it.isEmpty() }?.removeSurrounding("\"")
        if (fresh != null) lastSsid = fresh
        return lastSsid
    }

    companion object {
        private const val PLACEHOLDER_MAC = "02:00:00:00:00:00"
        private const val TAG = "LocalMdm.Wifi"
    }
}
