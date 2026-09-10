# Live qualification

The mocked suite proves the integration's half of the contract. These checks
need a real tablet and are recorded here with a date when they pass. Every row
is unverified until it has one.

| Check | How | Result |
| --- | --- | --- |
| DPC becomes Device Owner | `adb shell dpm set-device-owner ...`, app shows "active" | unverified |
| Foreground service starts on boot | reboot, `adb shell dumpsys activity services LocalMdm` | unverified |
| Status endpoint answers | `curl` with the token | unverified |
| Config flow completes | add the integration | unverified |
| Webhook URL reaches the tablet | `adb logcat -s LocalMdm.Http` shows the PUT | unverified |
| Camera round trip under 2 s | toggle the helper, compare the switch timestamp with `last_report` | unverified |
| Enforced sensor follows | `binary_sensor.<tablet>_camera_disabled_enforced` | unverified |
| Kiosk starts and stops | set packages, toggle kiosk, check `kiosk lock` sensor | unverified |
| Forbidden key refused by the DPC | `curl -X PUT` with `no_config_wifi` returns 422 | unverified |
| Token rotation triggers reauth | rotate on the tablet, watch for the repair | unverified |
| Wi-Fi remains user-configurable under every policy | open Settings, Connections while all switches are on | unverified |
| adb remains available under every policy | `adb devices` while all switches are on | unverified |
