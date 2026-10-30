# Decision 0001: Enhanced Tracking Protection stays off

- Status: **SUPERSEDED** by
  [decision 0002](0002-stock-etp-restored.md) (2026-10-30). Kept for the
  record; the ETP override described here is no longer in the tree.

## Decision

Enhanced Tracking Protection (ETP) stays off by bundle, permanently. The
ETP brand and UI are retired; the shields panel shows our own protections
instead. There is no plan to adopt ETP later ("archive and revisit" was
considered and rejected).

## Context

- User vote: ETP off by bundle.
- Offline by default: ETP depends on remotely updated lists. Aether ships
  no runtime list updates of any kind.
- No remote content, no Google in any form: ETP's supply chain (Disconnect
  list served through Mozilla Remote Settings, Safe Browsing adjacency)
  does not fit.
- Our own graded anti-fingerprinting system (units 125-132) covers the
  fingerprinting half of ETP deliberately, built from zero, without reusing
  the RFP model.

## What covers each ETP piece

| ETP piece | Aether answer |
|---|---|
| Known-fingerprinter blocking | Own module (`AetherFingerprinterBlock.sys.mjs`) over a vendored Disconnect snapshot frozen in-tree (`aether.blockKnownFingerprinters`, on; third-party loads only). Unit 124. |
| Storage partitioning, query stripping, bounce-tracking protection | Kept as-is. Unit 122. |
| Fingerprinting surface reduction | Own graded layers, each behind master + kill pref with per-site exemption (units 125-132). |
| ETP UI and brand | Retired to custom/off; the shields panel is our own (units 122-123). |

## Explicitly out of scope

Safe Browsing (malware/phishing) is a separate topic: philosophy requires
never breaking it without a replacement (own proxy planned). This record
covers tracking protection only.

## Consequences

- No ETP preference may be flipped back on as a side effect of later work;
  doing so needs a new decision record.
- The shields panel never references ETP behavior or copy.
