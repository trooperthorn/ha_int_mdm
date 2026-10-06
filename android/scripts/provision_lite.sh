#!/usr/bin/env bash
# Lite-tier provisioning for a tablet that cannot take a Device Owner
# (Fire OS ships Parental Controls as a protected profile owner). Everything
# here is a one-time adb grant; the DPC keeps the rest in step afterwards.
#
#   scripts/provision_lite.sh <adb serial> [path/to/app.apk] [path/to/companion-minimal.apk]
#
# What it does, and why each line is needed:
#   set-active-admin       lockNow and setCameraDisabled work for an active admin
#   WRITE_SECURE_SETTINGS  lets the DPC toggle stay-awake and screen pinning
#   GET_USAGE_STATS        lets HomeWatch see when the stock launcher comes to
#                          the front (Fire OS hides launcher window events from
#                          third-party accessibility services)
#   SYSTEM_ALERT_WINDOW    the lock splash may be drawn over the launcher
#   REQUEST_INSTALL_PACKAGES  lets install_package open the platform confirm
#                          dialog instead of being refused as an unknown source
# It never touches adb, Wi-Fi, or developer options.
# The companion APK (app-minimal-release.apk from fetch_companion_apk.sh
# minimal, since Fire OS has no Google services) is side-loaded here if
# given. Sign-in still has to happen on the tablet screen.
set -euo pipefail
serial="${1:?adb serial}"
apk="${2:-app/build/outputs/apk/release/app-release.apk}"
companion_apk="${3:-}"
pkg=com.trooperthorn.localmdm
adb="adb -s $serial"

$adb install -r "$apk"
if [ -n "$companion_apk" ]; then
  echo "Installing Companion (minimal): $companion_apk"
  $adb install -r "$companion_apk"
fi
$adb shell dpm set-active-admin "$pkg/.MdmDeviceAdminReceiver"
$adb shell pm grant "$pkg" android.permission.WRITE_SECURE_SETTINGS
$adb shell appops set "$pkg" GET_USAGE_STATS allow
$adb shell appops set "$pkg" SYSTEM_ALERT_WINDOW allow
$adb shell appops set "$pkg" REQUEST_INSTALL_PACKAGES allow
# Keep the DPC out of Doze's network cutoff; the entry survives reboots.
$adb shell dumpsys deviceidle whitelist +"$pkg" >/dev/null 2>&1 || true
$adb shell am start -n "$pkg/.MainActivity" >/dev/null
# Fire OS 7 (Android 9) does not randomise the Wi-Fi MAC, so the one in use
# is the one to reserve in UniFi (docs/onboarding.md, "Address plan").
factory_mac=""
current_mac=$($adb shell cat /sys/class/net/wlan0/address 2>/dev/null | tr -d '\r' || true)
echo "Lite tier provisioned on $serial. Open Local MDM on the tablet for the token; it reports tier=admin."
echo
echo "UniFi Network, before pairing (Client Devices > this tablet > Settings):"
echo "  Name      : <Room>-Tab, for example Kitchen-Tab"
echo "  Fixed IP  : on, an address in the tablet network"
echo "  MAC       : factory ${factory_mac:-<Settings > About tablet > Status>}; in use now ${current_mac:-unknown}"
echo "  On the tablet: Wi-Fi > this network > Privacy > Use device MAC, then reconnect."
echo "Home Assistant > Add integration > Local MDM then offers the tablet by name; only the token is typed."
if [ -n "$companion_apk" ]; then
  echo "Companion (minimal) is installed; sign in to it on the tablet screen with the Home Assistant URL and a user account."
fi
