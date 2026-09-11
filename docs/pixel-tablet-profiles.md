# Pixel Tablet: profile-based management (options, 2026-09-11)

Goal: a Pixel Tablet that is not a single-app console. It runs Home Assistant
plus a short list of other apps, and an admin picks a **security profile**
in Home Assistant that decides which apps and which restrictions apply.
Nothing here is implemented yet; this is the option set to choose from.

## What the Pixel Tablet allows

- Stock Android (16), Google Play system image. `dpm set-device-owner` works
  after a reset with no account, the same path as the Samsung. A Google
  account can be added **after** Device Owner is set, so Play and Google
  services keep working on a managed tablet; the DPC can later forbid
  further account changes with `DISALLOW_MODIFY_ACCOUNTS`.
- Hub Mode (dock, Assistant, ambient photos) needs the primary Google
  account and the tablet to be locked on the dock. It survives Device Owner
  as long as the account exists and lock task is not active; a full kiosk
  profile suppresses it.
- Everything the Samsung tier already enforces applies unchanged (lock
  task, restrictions, update policy, silent install, Wi-Fi provisioning).

## Enforcement mechanisms available for an app allowlist

| Mechanism | What the user sees | Strength | Notes |
| --- | --- | --- | --- |
| **Multi-app lock task** (`setLockTaskPackages` with the whole allowlist, DPC draws an app grid inside lock task) | A branded launcher with N tiles, no status bar drawer, no Settings, no notifications unless allowed by `setLockTaskFeatures` | Strongest | Needs a mini launcher activity in the DPC; Hub Mode off; Settings only through an allow-listed activity |
| **Suspend or hide everything else** (`setPackagesSuspended`, `setApplicationHidden`) with the stock launcher | Normal Pixel launcher, disallowed apps greyed out or gone, notifications work, Hub Mode works | Medium | User can still open Settings; pair with restrictions (`DISALLOW_INSTALL_APPS`, `DISALLOW_UNINSTALL_APPS`, `DISALLOW_MODIFY_ACCOUNTS`, `DISALLOW_ADD_USER`) |
| **Restrictions only** (no app control) | Normal tablet with guardrails | Light | Already covered by today's flags |
| **Managed profile** (work profile on a personal tablet) | Two app sets, badge on managed apps | Wrong fit | Manages only the work half; the personal half is unrestricted |

All four are Device Owner APIs the DPC already holds; none need Google's
Android Management API or Play EMM.

## Security profiles

A profile is a named bundle held on the Home Assistant side:

```yaml
profiles:
  console:            # the existing single-app kiosk
    mode: lock_task
    apps: [io.homeassistant.companion.android]
    flags: {kiosk_mode: true, status_bar_disabled: true, install_apps_blocked: true}
  family:
    mode: allowlist   # stock launcher, everything else suspended
    apps: [io.homeassistant.companion.android, com.spotify.music, com.netflix.mediaclient, com.google.android.apps.photos]
    flags: {install_apps_blocked: true, uninstall_apps_blocked: true, accounts_locked: true}
  guest:
    mode: lock_task_multi
    apps: [io.homeassistant.companion.android, com.google.android.youtube]
    flags: {camera_disabled: true, adjust_volume_blocked: false}
  locked:             # console lockout / threat
    mode: lock_task
    apps: [io.homeassistant.companion.android]
    flags: {kiosk_mode: true, status_bar_disabled: true}
```

Home Assistant exposes `select.<tablet>_security_profile` (admin-only in the
control panel; ordinary users see the state) and `local_mdm.apply_profile`.
Automations move a tablet between profiles: `locked` while the ELK is armed
or a threat is up, `family` in the evening, `guest` when a visitor is
present. The existing switches stay for one-off changes and always reflect
the enforced state.

### What changes in the protocol

New policy keys, all Device Owner only (the lite tier reports them
`unsupported`):

| Key | Type | Android call |
| --- | --- | --- |
| `app_mode` | `open` / `allowlist` / `lock_task_multi` (`kiosk_mode` stays the single-app case) | see table above |
| `allowed_packages` | list | with `allowlist`: every other launchable package suspended; with `lock_task_multi`: the lock task allow list and the grid |
| `accounts_locked` | bool | `DISALLOW_MODIFY_ACCOUNTS` |
| `add_user_blocked` | bool | `DISALLOW_ADD_USER` |
| `notifications_in_kiosk` | bool | `LOCK_TASK_FEATURE_NOTIFICATIONS` toggle |
| `settings_in_kiosk` | bool | allow-lists `com.android.settings` in lock task |

Forbidden-key guard unchanged: nothing here can touch Wi-Fi, adb, or the
management path. `allowed_packages` must always include the DPC and the
Companion app, and the DPC refuses an allowlist that would suspend the
current kiosk target.

### Where profiles live

Two choices, decide before coding:

1. **Integration options** (config entry options, edited in the UI): the
   profile table is per tablet, survives restarts, no YAML. Simple, but each
   tablet is edited separately.
2. **A YAML package** in `~/workspace/console-lockout`: profiles shared by
   all tablets, versioned with the rest of the console work, applied through
   `local_mdm.apply_policy` with the full document. Matches how the console
   lockout is built today.

Recommendation: 2 for the first pass (it needs only one new action and the
new keys), then 1 if the per-tablet edits become annoying.

## What to expect on the Pixel specifically

- Provisioning: reset, skip the account, `set-device-owner`, then add the
  Google account and lock accounts. Apps can then come from Play; the
  `install_package` action is still there for sideloads.
- `allowlist` mode keeps Hub Mode and the dock experience; `lock_task_multi`
  and `lock_task` do not.
- Android 16 lock task shows an inert navigation bar as on the Samsung; the
  DPC grid is the only way between apps inside it.
- Face and fingerprint unlock, screen lock and Assistant remain the user's;
  the DPC never sets a password policy (out of scope, and the reason is the
  same as for network: a wrong policy must never strand the tablet).

## Status (2026-09-11)

Steps 1, 2 and the action half of 4 shipped: `app_mode` (`open` /
`allowlist`), `allowed_packages`, `accounts_locked`, `add_user_blocked`, the
`select.<tablet>_app_mode` and `text.<tablet>_allowed_packages` entities, and
the `local_mdm.apply_policy` action that a YAML profile package drives
(docs/examples/security_profiles.yaml). Qualified on the Pixel Tablet
(Android 16) as Device Owner: see docs/live_qualification.md. Chosen: the
allowlist on the stock launcher, profiles in a YAML package.

Not started: `lock_task_multi` with the DPC grid launcher,
`notifications_in_kiosk`, `settings_in_kiosk`, and profiles as integration
options.

## Order of work if approved

1. Protocol keys and the forbidden-key checks on both sides, with tests.
2. `allowlist` mode (suspend/unsuspend) and the two account restrictions.
3. `lock_task_multi` with the DPC grid launcher (branded like the splash).
4. HA `apply_profile` action, the `security_profile` select, control panel
   view, console-lockout automations that switch profiles.
5. Pixel Tablet provisioning and qualification, Samsung regression pass.
