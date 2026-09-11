# Fire OS 7 assessment (Fire HD 8 Plus, 2020)

Assessed 2026-09-11 on Sean's KFONWI (Fire OS 7.3.2.9, Android 9, API 28),
with the Local MDM debug APK built after the Wi-Fi API guards.

## What works

- The DPC installs and runs on Android 9 (`minSdk 28`), so the code path is
  not the problem.
- adb, `pm`, `uiautomator` and `dpm` all behave as on stock Android.

## What blocks Device Owner

`dpm set-device-owner` fails with "Trying to set the device owner, but the
user already has a profile owner." The profile owner of user 0 is
`com.amazon.parentalcontrols/.receivers.ParentalAdminReceiver` ("Parental
Controls", `testOnlyAdmin=false`, policies force-lock and disable-camera).
Everything that normally clears a profile owner was tried:

| Attempt | Result |
| --- | --- |
| `dpm remove-active-admin com.amazon.parentalcontrols/...` | `SecurityException: Attempt to remove non-test admin` |
| `pm uninstall -k --user 0 com.amazon.parentalcontrols` | `DELETE_FAILED_INTERNAL_ERROR` (active admin) |
| Factory reset from Settings, then registration | profile owner and 8 Amazon accounts back, plus a child profile (user 10) |
| `pm remove-user 10`, then Deregister in Settings > My Account | user 10 gone, accounts down to 5 `amazon.account` entries, profile owner still present |

Amazon ships Parental Controls as the profile owner of the primary user on
Fire OS 7 and Android will not accept a Device Owner alongside it. Whether
a wipe followed by skipping Wi-Fi and registration boots without the
profile owner is untested; the deregistered state suggests it is set by
the system image, not by registration.

## Options for the four Fire tablets

1. **Do not manage Fires with Local MDM.** Cheapest; they stay consumer
   devices with Fire's own app pinning.
2. **A "lite" tier without Device Owner.** The DPC as a plain device admin
   plus HOME launcher, `startLockTask` in screen-pinning mode (Android shows
   a one-time "pin this screen" prompt instead of true lock task), silent
   install impossible (user must confirm each APK), no user restrictions,
   no system-update policy. Honest sensor set: `device_owner` off,
   `kiosk_lock` reflects pinning only. Real work: a second enforcement
   backend in `PolicyEngine`, entity availability by tier, docs.
3. **Custom ROM / Fire Toolbox route.** Out of scope: bootloader and
   warranty games, and it contradicts the "unrooted, vendor image" rule.

Recommendation: 1 for now, 2 only if a Fire is wanted as a locked console
and the honesty table in `docs/console-lockout.md` is extended for it.

## State left on the tablet

Deregistered from Amazon, child profile removed, Local MDM debug APK
installed (not owner). Re-register in Settings > My Account to return it to
normal use.
