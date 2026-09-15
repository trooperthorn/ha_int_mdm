# Documentation index

One line per document stating what it owns, so a reader knows where a fact belongs. Code
carries only what a reader needs at the point of reading; explanation lives here.

- `design.md`: the two-sided architecture, why the API client is separate from the
  entity lifecycle, push-first with poll fallback, desired versus enforced state.
- `protocol.md`: the HTTP contract between Home Assistant and the DPC, the policy
  document, and the DevicePolicyManager call behind each key.
- `security.md`: trust boundaries, the network-brick guard, what is enforced versus
  advisory, and what the design does not defend against.
- `onboarding.md`: the repeatable process for adding a tablet (tier choice, prepare, provision scripts, pair, Companion, profile, verify, gotchas)
- `provisioning-day-checklist.md`: printable run sheet for the adb pass, distilled from onboarding.md
- `operations.md`: test gate, release path, GitHub App, branch protection, runtime
  knobs, and troubleshooting.
- `decisions.md`: dated decisions with the alternative rejected and why.
- `backlog.md`: dated open items.
- `console-lockout.md`: the wall tablet recipe (Companion as the single app, automatic OS
  updates, stay awake) and how Device Owner changes the honesty table of a Companion-only
  design.
- `knox-sdk-assessment.md`: what the Samsung Knox SDK would add over the Device Owner
  APIs, its license and cloud dependencies, and why it is not used in this phase.
- `live_qualification.md`: the hardware checks that the mocked suite cannot replace.
