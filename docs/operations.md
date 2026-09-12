# Operations

## Test gate

The Home Assistant harness imports `fcntl`, so the suite runs in WSL Ubuntu
with Python 3.14, never on the Windows host:

```bash
wsl -e bash -lc 'cd /mnt/c/Users/<you>/repos/ha_int_mdm && ~/mdmvenv/bin/python -m pytest tests -q'
```

Venv: `python3.14 -m venv ~/mdmvenv && ~/mdmvenv/bin/pip install -r requirements_test.txt`.
The harness pin 0.13.364 installs core 2026.9.1; CI asserts that version.
The full gate is `ruff check`, `ruff format --check`, `mypy --python-version 3.14
custom_components/local_mdm/`, `pytest tests`, and
`python scripts/build_release_artifacts.py --validate-only`.

`tests/test_api.py` opens real sockets on localhost against an aiohttp test
server; it requests the harness's `socket_enabled` fixture for that.

`android.yml` compiles the debug APK on every push with the committed
wrapper (Gradle 9.7.1) on Temurin JDK 21 and checks the Gradle `versionName`
against the manifest. It is not a required check yet; add it to protection
after it has been green for a few merges. Locally: `cd android && ./gradlew
assembleDebug` with `JAVA_HOME` pointing at the Android Studio JBR.

## Release path

A merge to `main` is the release. `release.yml` reruns the test and validate
workflows, validates that `manifest.json` and `android/app/build.gradle.kts`
carry the same CalVer, builds `local_mdm.zip` deterministically, attaches an
SPDX SBOM, checksums, and provenance attestations, and publishes the tag
`vYYYY.MM.DD.N`. `prepare-release.yml` then opens the next bump PR through
the release GitHub App when a release-bearing path
(`custom_components/local_mdm`, `android`) changed. The App variable
`RELEASE_AUTOMATION_CLIENT_ID` and secret `RELEASE_AUTOMATION_PRIVATE_KEY`
must be set on the repository; the workflow fails before changing anything if
they are missing.

Verify a release:

```bash
gh release download v2026.09.10.1 -R trooperthorn/ha_int_mdm -p local_mdm.zip -p SHA256SUMS
sha256sum --check SHA256SUMS --ignore-missing
gh attestation verify local_mdm.zip -R trooperthorn/ha_int_mdm
```

The release job also builds the DPC and attaches `local-mdm-debug.apk`,
signed with the fleet keystore held in the `ANDROID_DEBUG_KEYSTORE_B64`
repository secret (base64 of `~/.android/debug.keystore`). The job fails
rather than publish a differently signed APK when the secret is missing;
the signer digest is printed in the job summary.

## Branch protection

Applied after the first green run on `main`, naming the job display names:
`pytest (Python 3.14)`, `HACS validation`, `hassfest (manifest sanity)`,
`CodeQL (python)`, `Python static security checks`. Strict, enforce admins,
conversation resolution, no force push, no deletion, zero required approvals.

## Runtime knobs

| Where | Knob | Effect |
| --- | --- | --- |
| Options flow | Poll interval (10 to 3600 s) | Fallback poll when a push is missed; entry reloads on save |
| Tablet app | Generate a new pairing token | Invalidates the old token; Home Assistant asks for reauth on the next request |
| `MdmService.PORT` | 8484 | Compile-time; change both sides together |
| `HEARTBEAT_MS` | five minutes | Unsolicited report cadence from the tablet |

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Setup says cannot connect | `curl -H "Authorization: Bearer <token>" http://<tablet>:8484/v1/status` from the Home Assistant host |
| Setup retries with "Could not register the webhook" | The status call worked but the webhook PUT did not; look at `adb logcat -s LocalMdm.Http` |
| Switch turns on, enforced sensor stays off | Read the switch's `enforcement` attribute: `refused` means not Device Owner, `failed` means a platform exception in `adb logcat -s LocalMdm.Policy` |
| `last_report` stops updating | The tablet's report is not reaching the webhook: wrong internal URL, or the source address is not local. Reload the entry to resend the URL |
| Reauth prompt after rotating the token | Expected; enter the new token |
| Kiosk switch refuses to turn on | The kiosk packages text entity is empty; set at least one package name |
