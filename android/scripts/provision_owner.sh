#!/usr/bin/env bash
# Device Owner provisioning for a tablet that can take one (Samsung, Pixel,
# stock Android). Run once per tablet over USB after the checks below pass.
#
#   scripts/provision_owner.sh <adb serial> [path/to/app.apk] [path/to/companion.apk]
#
# Preconditions it verifies before touching the tablet:
#   - exactly one user (a supervised child user blocks set-device-owner)
#   - no accounts (remove them in Settings > Passwords & accounts; add back after)
#   - the DPC is not already the owner (safe to re-run for a reinstall)
# It never touches adb, Wi-Fi, or developer options: those are the recovery path.
# The companion APK (app-full-release.apk from fetch_companion_apk.sh full) is
# side-loaded in the same pass if given; sign-in still has to happen on the
# tablet screen, adb cannot do that part.
set -euo pipefail
serial="${1:?adb serial}"
apk="${2:-app/build/outputs/apk/release/app-release.apk}"
companion_apk="${3:-}"
pkg=com.trooperthorn.localmdm
admin="$pkg/.MdmDeviceAdminReceiver"
adb="adb -s $serial"

echo "== $serial: $($adb shell getprop ro.product.model | tr -d '\r') Android $($adb shell getprop ro.build.version.release | tr -d '\r')"

users=$($adb shell pm list users | grep -c 'UserInfo{' || true)
if [ "$users" -ne 1 ]; then
  echo "Refusing: $users users on the tablet; remove the extra user in Settings > System > Users first." >&2
  exit 2
fi
accounts=$($adb shell dumpsys account | grep -c 'Account {' || true)
if [ "$accounts" -ne 0 ]; then
  echo "Refusing: $accounts account(s) on the tablet; remove them in Settings > Passwords & accounts, add them back after provisioning." >&2
  exit 2
fi

$adb install -r "$apk"
if $adb shell dumpsys device_policy | grep -q "Device Owner"; then
  echo "Device Owner already set; APK updated in place."
else
  $adb shell dpm set-device-owner "$admin"
fi
if [ -n "$companion_apk" ]; then
  echo "Installing Companion: $companion_apk"
  $adb install -r "$companion_apk"
fi

# Keep the DPC out of Doze's network cutoff so Home Assistant can reach it
# on battery; the allowlist entry survives reboots.
$adb shell dumpsys deviceidle whitelist +"$pkg" >/dev/null 2>&1 || true

$adb shell am start -n "$pkg/.MainActivity" >/dev/null 2>&1 || true
sleep 3
ip=$($adb shell ip -4 addr show wlan0 2>/dev/null | grep -oE 'inet [0-9.]+' | cut -d' ' -f2 || true)
token=$($adb shell "run-as $pkg cat shared_prefs/local_mdm.xml" 2>/dev/null | grep -oE 'name="token">[^<]+' | cut -d'>' -f2 || true)

# UniFi address plan (docs/onboarding.md, "Address plan"): the tablet gets a
# fixed IP reserved against its MAC and a client name of the form Room-Tab.
# Android randomises the Wi-Fi MAC per network and again after a reset, which
# silently breaks a reservation, so reserve the factory MAC (reported by the
# DPC to a Device Owner) and set the tablet's Wi-Fi network to "Use device MAC".
factory_mac=""
if [ -n "$token" ]; then
  $adb forward tcp:18484 tcp:8484 >/dev/null 2>&1 || true
  factory_mac=$(curl -fsS -m 5 -H "Authorization: Bearer $token" http://127.0.0.1:18484/v1/status 2>/dev/null \
    | grep -oE '"mac_factory":"[0-9a-fA-F:]{17}"' | cut -d'"' -f4 || true)
  $adb forward --remove tcp:18484 >/dev/null 2>&1 || true
fi
current_mac=$($adb shell cat /sys/class/net/wlan0/address 2>/dev/null | tr -d '\r' || true)

echo
echo "Provisioned as Device Owner."
echo "  Address : ${ip:-<read from the app screen>}:8484"
echo "  Token   : ${token:-<read from the app screen; release builds do not expose it over adb>}"
echo
echo "UniFi Network, before pairing (Client Devices > this tablet > Settings):"
echo "  Name      : <Room>-Tab, for example Kitchen-Tab"
echo "  Fixed IP  : on, an address in the tablet network"
echo "  MAC       : factory ${factory_mac:-<Settings > About tablet > Status>}; in use now ${current_mac:-unknown}"
echo "  On the tablet: Wi-Fi > this network > Privacy > Use device MAC, then reconnect."
echo "Home Assistant > Add integration > Local MDM then offers the tablet by name; only the token is typed."
echo "Next: Home Assistant > Settings > Devices & services > Add integration > Local MDM, pick the tablet (or enter the address) and the token."
echo "Then add the Google account back on the tablet if it needs one, before applying a profile that locks accounts."
if [ -n "$companion_apk" ]; then
  echo "Companion is installed; sign in to it on the tablet screen with the Home Assistant URL and a user account."
fi
