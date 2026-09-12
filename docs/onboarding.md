# Onboarding a tablet

The repeatable process for adding a tablet to Local MDM, written so that
anyone with the tablet, a USB cable, adb, and access to Home Assistant can do
it without help. Every step was run on the fleet listed at the end; the
gotchas are things that actually happened.

## 0. What you need

- The DPC APK: `local-mdm-debug.apk` from the current GitHub release
  (v2026.09.12.1 or later). Every release carries it, signed with the
  fleet's keystore so it updates enrolled tablets in place. Verify it with
  the release's SHA256SUMS. To build it yourself instead, the keystore in
  `~/.android/debug.keystore` on the provisioning computer must be the
  fleet one:

  ```bash
  cd android && JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ANDROID_HOME="$LOCALAPPDATA/Android/Sdk" ./gradlew assembleDebug
  ```

- adb on the computer (`platform-tools`), and a USB cable that carries data.
- Home Assistant with Local MDM v2026.09.11.8 or later installed from HACS.
- For a Fire tablet: the Companion **minimal** APK from the
  home-assistant/android releases (Fire OS has no Google services).

## 1. Decide the tier

| Tablet | Tier | Why |
| --- | --- | --- |
| Samsung Galaxy Tab, Pixel Tablet, any stock Android | Device Owner | Full policy set |
| Amazon Fire (Fire OS 7/8) | Lite (device admin) | Fire OS ships a protected profile owner; Device Owner is impossible (docs/fire-os-assessment.md) |

## 2. Prepare the tablet

Device Owner tablets:

1. Fresh from the box or factory reset: skip every account step in setup.
   An already-set-up tablet works too, as long as you remove every account
   (Settings > Passwords & accounts) and every extra user (Settings > System
   > Users). Android names the blocker if one remains.
2. Settings > About tablet > tap Build number seven times, then Settings >
   System > Developer options > USB debugging on.
3. Join the tablet to the tablet Wi-Fi network (the one Home Assistant can
   reach, not the guest network).
4. Plug in, accept "Allow USB debugging" with "Always allow from this
   computer".

Fire tablets:

1. Factory reset from Settings. In setup, Fire OS makes you try a Wi-Fi
   network; let one join attempt fail, then Back lets you skip Wi-Fi. Skip
   registration.
2. Settings > Device Options > tap Serial number seven times, then Developer
   Options > ADB on. Accept the prompt on USB.
3. Join Wi-Fi afterwards from Settings.

## 3. Provision

From the `android/` folder of this repository:

```bash
# Device Owner
scripts/provision_owner.sh <adb serial> path/to/local-mdm-debug.apk

# Fire (lite)
scripts/provision_lite.sh <adb serial> path/to/local-mdm-debug.apk
```

`adb devices` shows the serial. Both scripts print the tablet's address and
token at the end (or tell you to read them from the app's screen). The
owner script refuses to run while accounts or extra users remain.

## 4. Pair with Home Assistant

Settings > Devices & services > Add integration > Local MDM: enter the
address, port 8484, and the token. The device appears as "Tablet <id>";
rename it on its device page. The management tier sensor reads `owner` or
`admin`.

Then, on the device page:

- Set **Kiosk packages** to the kiosk app. Samsung and Pixel:
  `io.homeassistant.companion.android`. Fire:
  `io.homeassistant.companion.android.minimal` (the suffix matters).
- Turn on the switches the tablet needs, or select a profile (step 6).

## 5. Install and sign in to Companion

Device Owner tablets with a Google account: install Companion from Play
after adding the account back. Otherwise, and on every Fire, use the
`local_mdm.install_package` action with the release APK URL and its SHA-256.
On the lite tier the tablet shows the platform's install dialog; tap
Install there. The app installs blocked switch must be off for the install
to go through, on every tier.

Sign in to Companion on the tablet with the Home Assistant URL and a user
account. This is the one step nobody can do over adb.

## 6. Apply a profile (optional)

The security profile package (docs/examples/security_profiles.yaml) defines
console, family, guest and locked. Add an `input_select` and automation for
the new tablet with its device id (device page URL), or call
`script.apply_security_profile` directly with `device_id` and `profile`.

Add the Google account back **before** a profile that locks accounts.

## 7. Verify

On the device page: Device owner on (or tier admin on a Fire), enforcement
failures 0, kiosk lock reads Locked when kiosk is on. On the tablet: a
reboot lands in the lock splash and then the kiosk app. In the log:

```bash
adb -s <serial> logcat -s LocalMdm.Policy LocalMdm.Http LocalMdm.Webhook
```

## Known gotchas

- **PIN plus automatic OS updates.** After an OS update the tablet reboots
  and waits at the lock screen; nothing, including the DPC, runs until
  someone unlocks it once. Console tablets should have no PIN. A tablet
  with a PIN needs a hands-on unlock after each update (Pixel, 2026-09-11).
- **Android 17 shell.** The adb shell can no longer see third-party apps, so
  `am start`, `monkey` and `pm resolve-activity` fail against every
  sideloaded app. The DPC's own actions from Home Assistant are unaffected.
- **Install block covers everything.** `install_apps_blocked` stops Play,
  sideloads, adb installs, and the DPC's own `install_package`. Turn it off
  for the install, then back on.
- **Play Store cannot be suspended.** The allowlist leaves it alone; use the
  install block to stop installs from it.
- **Fire OS.** The generic HOME intent on an unregistered Fire resolves to
  Amazon's setup activity; only the Companion minimal build runs; the lite
  kiosk is a launcher redirect, not lock task.
- **Lite tier self-update.** Updating the DPC through its own install action
  leaves `last_install` at awaiting_user; the update still applies.

## Fleet as of 2026-09-12

| Tablet | Tier | Kiosk package | Notes |
| --- | --- | --- | --- |
| Samsung Galaxy Tab A11+ (SM-X230) | owner | Companion full | console tablet, single-app kiosk |
| Pixel Tablet (tangorpro, Android 17) | owner | Companion full | family profile, allowlist, PIN set |
| Fire HD 8 Plus (KFONWI, Fire OS 7) | admin | Companion minimal | lite kiosk via launcher redirect |
