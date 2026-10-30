# Decision 0002: stock ETP restored, own adblock removed

- Status: **CLOSED** (decided 2026-10-30, Aetherfox 0.1 / Firefox 156.0.1)
- Supersedes [decision 0001](0001-etp-stays-off.md).

## Decision

Aetherfox ships no ad blocker of its own: no engine, no bundled or remote
filter lists, no adblock panel or settings section. Stock Enhanced Tracking
Protection is left exactly as Firefox ships it; the prefs that retired ETP
(`browser.contentblocking.category=custom` and the
`privacy.trackingprotection.*` overrides) are gone from the stack.

The project's own fingerprinting work stays untouched: graded layers, per-site
exemptions, the shields panel and the frozen known-fingerprinter guard.

## Context

- User decision (2026-10-30): keep the project's fingerprinting work, delete
  everything adblock-related, and ship that state in 0.1.
- The ETP override only existed to make room for the native blocker. With the
  blocker gone it had no owner and would have left every user on a custom,
  fully disabled tracking-protection category.
- The blocker carried ~3.4k lines of engine code and a 3.7 MB list snapshot;
  removing it also removes the largest patch from the public stack.

## Consequences

- Removing the override restores upstream defaults. Standard ETP is active
  again, and whatever list plumbing upstream uses stays upstream's business:
  Aetherfox configures neither ETP nor any list update.
- The shields panel keeps the fingerprinting master, the per-site exemption
  and the link to the fingerprint settings; it no longer mentions adblock.
- Patches 16-18 of the old stack (engine, adblock sections, polish) are gone;
  the remaining groups were renumbered.
- No adblock preference, module or string may be reintroduced as a side
  effect of later work; doing so needs a new decision record.
