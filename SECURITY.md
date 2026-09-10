# Security Policy

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private
addresses, or logs. Use GitHub's private vulnerability-reporting feature for
this repository. If private reporting is unavailable, open a minimal issue
asking the maintainer to establish a private channel; omit technical details.

Include the affected version/commit, prerequisites, impact, a minimal
reproduction, and suggested remediation. Remove tokens, pairing codes,
usernames, and private network details.

## Response targets

These are project targets, not an SLA: acknowledge critical/high reports in
three business days, establish severity and containment in seven, and publish
a coordinated fix/advisory as soon as safely validated. Lower-severity issues
are prioritized by exploitability and impact.

## Supported version

Only the latest published release and the default branch receive security
fixes. Operators should update Home Assistant and the Local MDM DPC promptly
and retain a tested rollback/backup.

## Security boundaries

Local MDM is a local control plane for an Android Device Owner app. Anyone who
can reach the tablet's HTTP port and holds the pairing token can change the
tablet's policy; anyone who can reach Home Assistant's webhook path from the
local network can inject a state report. It does not replace network
segmentation, and the policy guard that refuses network-severing restrictions
is a safety control against operator error, not a defense against a hostile
Home Assistant instance. docs/security.md carries the full model.
