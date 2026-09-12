#!/usr/bin/env bash
# Device Owner provisioning for a tablet that can take one (Samsung, Pixel,
# stock Android). Run once per tablet over USB after the checks below pass.
#
#   scripts/provision_owner.sh <adb serial> [path/to/app.apk]
#
# Preconditions it verifies before touching the tablet:
#   - exactly one user (a supervised child user blocks set-device-owner)
#   - no accounts (remove them in Settings > Passwords & accounts; add back after)
#   - the DPC is not already the owner (safe to re-run for a reinstall)
# It never touches adb, Wi-Fi, or developer options: those are the recovery path.
set -euo pipefail
serial="${1:?adb serial}"
apk="${2:-app/build/outputs/apk/release/app-release.apk}"
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
$adb shell am start -n "$pkg/.MainActivity" >/dev/null 2>&1 || true
sleep 3
ip=$($adb shell ip -4 addr show wlan0 2>/dev/null | grep -oE 'inet [0-9.]+' | cut -d' ' -f2 || true)
token=$($adb shell "run-as $pkg cat shared_prefs/local_mdm.xml" 2>/dev/null | grep -oE 'name="token">[^<]+' | cut -d'>' -f2 || true)

echo
echo "Provisioned as Device Owner."
echo "  Address : ${ip:-<read from the app screen>}:8484"
echo "  Token   : ${token:-<read from the app screen; release builds do not expose it over adb>}"
echo "Next: Home Assistant > Settings > Devices & services > Add integration > Local MDM, enter the address and token."
echo "Then add the Google account back on the tablet if it needs one, before applying a profile that locks accounts."
