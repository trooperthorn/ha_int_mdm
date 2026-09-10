# Local MDM Device Policy Controller

The Android half. It becomes Device Owner, runs an HTTP endpoint on port 8484
for Home Assistant, applies policy through `DevicePolicyManager`, and reports
back to a Home Assistant webhook.

Status: written against the public Android API, not yet compiled or run on a
tablet. Treat every line as unverified until docs/live_qualification.md records
a pass.

## Build

Requires Android Studio Ladybug or newer, or a command-line SDK with build
tools 35 and JDK 17. No Gradle wrapper is committed; generate one with a local
Gradle 8.9 or newer:

```bash
cd android
gradle wrapper --gradle-version 8.9
./gradlew assembleRelease
```

The release build is unsigned; sign it with your own key. Never publish the
key or a signed APK in this repository.

## Provision

1. Factory reset the tablet and skip every account step in setup. Device
   Owner cannot be set once an account exists.
2. Enable developer options and USB debugging.
3. Install and promote:

```bash
adb install app/build/outputs/apk/release/app-release.apk
adb shell dpm set-device-owner com.trooperthorn.localmdm/.MdmDeviceAdminReceiver
```

4. Open the app. It shows "Device Owner: active", the address, and the token.
   Enter those in Home Assistant.

The app never disables adb. Keep USB debugging on; it is the recovery path if
a policy misbehaves.

## Verify on the tablet

```bash
adb shell dumpsys device_policy | head -40
adb logcat -s LocalMdm.Policy LocalMdm.Http LocalMdm.Webhook
curl -H "Authorization: Bearer <token>" http://<tablet>:8484/v1/status
```

## Recovery

- Wrong token: open the app and tap "Generate a new pairing token", then
  reauthenticate in Home Assistant.
- Stuck in kiosk: `adb shell am start -n com.trooperthorn.localmdm/.KioskActivity --ez stop true`,
  or push a policy with `kiosk_mode: false`.
- Everything else: `adb shell dpm remove-active-admin` does not work on a
  Device Owner; a factory reset is the only removal path.
