# Design

## The two halves

Android only lets a Device Owner application change device policy, and only
from inside the device. So the enforcer has to be an app on the tablet, and
the control plane has to talk to it over the network. Google's Android
Management API does this by routing every policy through Google's cloud; this
project replaces that hop with a direct HTTP call on the LAN.

```text
Home Assistant                                   Tablet
+--------------------------+                     +---------------------------+
| local_mdm integration    |  PUT /v1/policy     | Local MDM DPC             |
|  coordinator ------------+-------------------->|  HttpServer -> PolicyEngine|
|  (desired policy)        |  GET /v1/status     |   -> DevicePolicyManager  |
|                          |<--------------------+                           |
|  webhook /api/webhook/id |  POST report        |  WebhookReporter          |
|  (local_only)   <--------+---------------------+   (after apply, 5 min,    |
+--------------------------+                     |    boot)                  |
                                                 +---------------------------+
```

## Layering inside the integration

Debugging a previous integration was slow because raw API handling, Home
Assistant state, and Jinja-visible attributes were tangled in one place. Here
the layers are strict:

| Layer | File | Imports Home Assistant? | Knows about |
| --- | --- | --- | --- |
| Policy model and guard | `policy.py` | no | key names, forbidden keys |
| HTTP client | `api.py` | no | endpoints, status document, typed errors |
| Coordinator | `coordinator.py` | yes | desired policy, push, poll, webhook merge |
| Entities | `switch.py`, `binary_sensor.py`, `sensor.py`, `button.py` | yes | how to display a `DeviceStatus` |

`api.py` and `policy.py` can be exercised from a plain Python shell against a
real tablet, which is how a protocol problem is separated from an entity
problem. Entities never call the client; they call the coordinator.

## Desired versus enforced

A switch shows what Home Assistant asked for. The matching `_enforced` binary
sensor shows what the tablet says it did. They differ when:

- the tablet is not Device Owner (every key `refused`),
- a DevicePolicyManager call threw (`failed`),
- the report has not arrived yet.

The `enforcement_problem` sensor is on whenever any key is not `applied`, so
one automation can alert on drift for every policy.

## Push first, poll fallback

The DPC POSTs its full status document after every policy apply, on boot, and
every five minutes. The integration's coordinator treats that as
`async_set_updated_data`. The poll interval (default 60 s, options flow)
exists for a missed push, for example when Home Assistant restarted and the
tablet's report went to a closed port.

A policy push is synchronous: the switch call returns after the DPC has
applied the policy and answered with the new status. The webhook report that
follows is the second confirmation. The acceptance test in
`tests/test_round_trip.py` measures switch call plus webhook delivery and
asserts under two seconds.

## Source of truth after restart

The tablet persists its applied policy; Home Assistant does not persist the
desired policy. On setup the coordinator reads the tablet's policy and adopts
it as desired. That means a restart of Home Assistant never silently
unrestricts a tablet, and a restored backup of Home Assistant cannot push a
stale policy on start.

## Policy version

Every push carries a monotonically increasing version. The DPC stores it and
reports it back, so a report that arrives after a newer push can be recognized
as stale by comparing `policy_version` (the coordinator keeps the maximum seen).
