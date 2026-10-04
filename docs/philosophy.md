# Aether philosophy

1. Privacy by default, explicit consent. Zero requests on first run until
   the user accepts in `aether://setup`.
2. No bloat, no noise, no ads. Minimal new-tab page, no Pocket, no sponsored
   content.
3. Unbiased ad blocking: the blocking engine is integrated natively
   (own code inspired by uBlock Origin and Brave), with no paid
   allowlist. Filter lists ship as per-release snapshots; automatic or
   manual updates are the user's choice.
4. No Mozilla dependencies by default: telemetry, Normandy, Shield and
   studies are off at compile time (`mozconfig`), by preference and by
   policy.
5. Security first: follow every Rapid release tag to tag, shipping within
   72 hours of an upstream security fix. Never break Safe Browsing without
   a replacement (own proxy planned).
6. Transparency: everything public, readable history, reproducible builds
   from the public repository, signed and immutable releases.