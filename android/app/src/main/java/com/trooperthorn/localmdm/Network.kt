package com.trooperthorn.localmdm

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import java.net.Inet4Address
import java.net.NetworkInterface

object Network {
    fun isWifiConnected(context: Context): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
    }

    /** First non-loopback IPv4 address, for display on the pairing screen. */
    fun localAddress(): String? = NetworkInterface.getNetworkInterfaces()?.toList()
        ?.filter { it.isUp && !it.isLoopback }
        ?.flatMap { it.inetAddresses.toList() }
        ?.firstOrNull { it is Inet4Address }
        ?.hostAddress
}
