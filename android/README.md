# Local MDM Device Policy Controller

The Android half. It becomes Device Owner, runs an HTTP endpoint on port 8484
for Home Assistant, applies policy through `DevicePolicyManager`, and reports
back to a Home Assistant webhook.

Status: compiles with AGP 9.4.0 on Gradle 9.7.1 and passed the Device Owner
round trip on an Android 15 emulator on 2026-09-10; see
docs/live_qualification.md for what was and was not observed.

## Build

Requires a JDK 17 or newer (the Android Studio bundled JDK 25 works) and an
Android SDK with platform 35. The Gradle wrapper is committed and pins
Gradle 9.7.1; AGP 9.4.0 applies Kotlin itself, so no Kotlin plugin is declared.

```bash
cd android
./gradlew assembleDebug
./gradlew assembleRelease
```

On Windows set `JAVA_HOME` to `C:\Program Files\Android\Android Studio\jbr`
and `ANDROID_HOME` to `%LOCALAPPDATA%\Android\Sdk` first. AGP 8.x cannot
run on Gradle 9.6 or newer (it used an internal Gradle API), which is why the
project is on AGP 9.

The release build is unsigned; sign it with your own key. Never publish the
key or a signed APK in this repository.

## Emulator for provisioning tests

Google Play system images refuse `dpm set-device-owner`; use a `google_apis`
image:

```bash
sdkmanager "system-images;android-35;google_apis;x86_64"
avdmanager create avd -n mdm_test -k "system-images;android-35;google_apis;x86_64" -d pixel_tablet
emulator -avd mdm_test -no-snapshot
adb -s emulator-5554 forward tcp:28484 tcp:8484
adb -s emulator-5554 reverse tcp:8123 tcp:8123
```

The forward exposes the DPC on the host at 127.0.0.1:28484; the reverse lets
the DPC reach a host receiver at 127.0.0.1:8123 as the webhook target.

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
