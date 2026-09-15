# Provisioning day checklist

A printable, tick-through version of docs/onboarding.md for the person doing
the adb step. One pass per tablet; Device Owner and Fire (lite) branches are
marked. Full detail and gotchas stay in onboarding.md — this is the run
sheet, not the reference.

## Before you start

- [ ] Provisioning laptop with adb (`platform-tools`) installed.
- [ ] USB cable that carries data, not a charge-only cable.
- [ ] `local-mdm-debug.apk` downloaded from the current GitHub release
      (v2026.09.12.1 or later), SHA256SUMS verified.
- [ ] Home Assistant reachable, Local MDM v2026.09.11.8 or later installed.
- [ ] Tablet Wi-Fi network name and password (must be the network Home
      Assistant is on, not a guest network).
- [ ] Companion APK fetched and digest-verified for the tablet's flavor:
      `scripts/fetch_companion_apk.sh full` (Samsung/Pixel) or
      `scripts/fetch_companion_apk.sh minimal` (Fire).
- [ ] Know the tier before you touch the tablet:

  | Tablet | Tier |
  | --- | --- |
  | Samsung Galaxy Tab, Pixel Tablet, any stock Android | Device Owner |
  | Amazon Fire (Fire OS 7/8) | Lite (device admin) |

## 1. Prepare the tablet

**Device Owner tablets**

- [ ] Factory reset, or if already set up: remove every account (Settings >
      Passwords & accounts) and every extra user (Settings > System > Users).
- [ ] Skip every account step during setup.
- [ ] Settings > About tablet > tap Build number 7 times, then Settings >
      System > Developer options > USB debugging on.
- [ ] Join the tablet Wi-Fi network.
- [ ] Plug in the USB cable, accept "Allow USB debugging?" with **Always
      allow from this computer**.

**Fire tablets**

- [ ] Factory reset from Settings.
- [ ] In setup, let one Wi-Fi join attempt fail, then Back to skip Wi-Fi.
      Skip registration.
- [ ] Settings > Device Options > tap Serial number 7 times, then Developer
      Options > ADB on. Accept the USB prompt.
- [ ] Join Wi-Fi afterwards from Settings.

## 2. Provision

From the `android/` folder of this repository:

- [ ] Confirm the tablet shows up: `adb devices`
- [ ] Device Owner tablet:
      `scripts/provision_owner.sh <adb serial> path/to/local-mdm-debug.apk app-full-release.apk`
- [ ] Fire tablet:
      `scripts/provision_lite.sh <adb serial> path/to/local-mdm-debug.apk app-minimal-release.apk`
- [ ] Script printed an address and token (or told you to read them off the
      app screen) — write them down before moving on. Companion is now
      installed on the tablet, signed out.
- [ ] Owner script refused to run? An account or extra user is still on the
      tablet — back to step 1.

## 3. Pair with Home Assistant

- [ ] Settings > Devices & services > Add integration > Local MDM.
- [ ] Enter address, port `8484`, and the token.
- [ ] Device appears as "Tablet `<id>`" — rename it on its device page.
- [ ] Management tier sensor reads `owner` (Device Owner) or `admin` (Fire).

## 4. Set kiosk package and switches

- [ ] Kiosk packages set to the kiosk app:
  - Samsung / Pixel: `io.homeassistant.companion.android`
  - Fire: `io.homeassistant.companion.android.minimal`
- [ ] Turn on the switches this tablet needs, or select a profile (step 6).

## 5. Sign in to Companion

Companion is already installed from step 2 — this step is on-screen only.

- [ ] Device Owner tablet that will carry a Google account: add the account
      back now (not required to sign in, just lets Play update Companion
      later).
- [ ] On the tablet: sign in to Companion with the Home Assistant URL and a
      user account. Nobody can do this step over adb — it has to happen on
      the screen.
- [ ] Skipped the companion APK in step 2, or provisioning an older release?
      Turn **install apps blocked** off, call `local_mdm.install_package`
      with the release APK URL and SHA-256, tap Install on the tablet if
      prompted (lite tier), then turn **install apps blocked** back on.

## 6. Apply a profile (optional)

- [ ] Add the Google account back **before** applying a profile that locks
      accounts, not after.
- [ ] Add an `input_select` and automation for the tablet's device id (from
      the device page URL), or call `script.apply_security_profile` with
      `device_id` and `profile` directly. Profiles are defined in
      docs/examples/security_profiles.yaml.

## 7. Verify before you walk away

- [ ] Device page shows Device owner on (or tier `admin` on a Fire).
- [ ] Enforcement failures: 0.
- [ ] Kiosk lock reads Locked, if kiosk is on.
- [ ] Reboot the tablet: it lands in the lock splash, then the kiosk app.
- [ ] If something looks wrong, check the log:
      `adb -s <serial> logcat -s LocalMdm.Policy LocalMdm.Http LocalMdm.Webhook`

## If it goes sideways

- Wrong token: open the app, tap "Generate a new pairing token", pair again.
- Stuck in kiosk:
  `adb shell am start -n com.trooperthorn.localmdm/.KioskActivity --ez stop true`,
  or push a policy with `kiosk_mode: false`.
- Nothing else works: a factory reset is the only removal path for a Device
  Owner tablet — `adb shell dpm remove-active-admin` does not work on one.
- No PIN on console tablets. A tablet with a PIN needs a hands-on unlock
  after every OS update, before the DPC runs again.

## Not on this checklist

There is no self-service path for the end user — every tablet needs this
adb pass from a provisioning laptop before anyone signs in. See
docs/decisions.md ("custom DPC over the Android Management API") for why:
zero-touch/QR enrollment routes through Google's cloud, which the
local-only design rejects.
