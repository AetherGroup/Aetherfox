<p align="center">
  <img src="branding/content/aether-lockup.png" alt="Aetherfox" width="200">
</p>

<p align="center">
  <strong>Soft-fork of Firefox with the telemetry taken out.</strong><br>
  Inspired by <a href="https://github.com/imputnet/helium">Helium</a>.
</p>

<p align="center">
  <sub>Windows x64 &middot; Firefox 156.0.1 &middot; pre-release, binaries unsigned</sub>
</p>

---

> **Working on this repo?** Read [AGENTS.md](AGENTS.md) first. It has the exact
> setup order, how the patch stack works and the five verification gates you
> must pass before committing.

> **Pre-release.** There is no public release yet, so there is no download and
> no update server. See [Current status](#current-status).

## Model

Aetherfox is not a divergent hard fork. It pins an official Firefox release,
clones it clean, and applies a stack of patches on top.

**The patches are the source.** Everything in this repository is what Aetherfox
changes relative to upstream Firefox, grouped in 18 thematic units. There is
no proprietary blob and no hidden code path.

```
firefox_version.txt      pinned upstream tag (FIREFOX_156_0_1_RELEASE)
patches/series           ordered list of patch groups
patches/core/*.patch     the changes (each carries its history)
branding/                name, icons, logo, about dialog
defaults/prefs/          sealed preferences
scripts/                 sync, build, package, updater tooling
```

Because Firefox itself is public, anyone can reproduce the exact browser.

---

## What's in the browser

**A native ad blocker**, designed from scratch around the established
open-source filter-list formats. Snapshot lists ship with the browser and
refresh from the same public sources; per-site switches decide what runs
where.

**Graded anti-fingerprinting protections.** Quiet layers that never break
sites, plus stricter ones for those who want them, each with its own switch
and a master switch above them all. Blocking known fingerprinting scripts
stays separate and always available.

**Its own settings page.** `about:aethersettings` replaces stock
`about:preferences` piece by piece: the same controls in a new design, with
nothing left that phones home.

**Its own installer and update channel.** `AetherfoxSetup-<version>.exe` is a
single-file offline setup (it installs with no network), on its own
`aether-release` update channel. The uninstaller ships inside the browser and
the build fails if it ever goes missing.

**Optional Features.** Anything that talks to a service is off by default and
waits behind an explicit switch that states what it sends before you turn it
on.

---

## What's taken out

**Firefox Sync and accounts**, entirely: the UI, the strings and the sync
subtrees. **Normandy, Shield and studies**: no experiment enrollment.

**Telemetry**, which is the bulk of the work. It is a deletion job rather
than a preference job: a metric or ping that nothing submits any more is
removed from the tree, not switched off.

- Legacy telemetry and the Glean upload paths are disabled **at build time**,
  so they do not depend on a preference surviving an upgrade.
- Dead metric definitions, unused pings and the Glean DOM bindings are
  deleted from the tree — a few thousand files, most of them deletions.
- The crash reporter is compiled out, so crash data cannot leave the machine.
- Pocket, sponsored content and attribution pings.
- Remote-settings endpoints for Merino and the new-tab feeds.
- The OpenTelemetry tracing component (`gecko-trace`), already inert in
  release builds.

Anything that genuinely needs to talk to a service is not deleted: it is off
by default and waits behind an explicit switch.

---

## Current status

- Pre-release: binaries are **not code-signed** (SmartScreen will warn).
- **Updates run in localhost mode for now**: the updater talks to a local
  `scripts/aus-local.py` serving a locally built MAR. It moves to the real
  update service once that launches; until then there is no public update
  server.
- **Windows x64 only.** macOS and Linux are not set up.
- `https://aethergroup.github.io/aetherfox/news` sits in the release-notes prefs until the
  site has the real page.

### Known gaps

- The old `about:preferences` is still in the tree while its options keep
  moving to the new settings page; it is deleted once the port is complete.

---

## Building

Requires Windows, MozillaBuild and Visual Studio 2022 Build Tools. Full
instructions, including troubleshooting, in [docs/BUILD.md](docs/BUILD.md).

```powershell
git clone https://github.com/AetherGroup/Aetherfox
cd Aetherfox

python scripts\sync.py --src C:\o\fs --apply --no-download
$env:MOZCONFIG = "C:\o\browser\mozconfig.windows"
scripts\windows\run-bootstrap.cmd   # once per machine
scripts\windows\run-build.cmd
scripts\windows\run-package.cmd
python scripts\verify-flags.py --objdir C:\o\fs\obj-aether
C:\o\fs\obj-aether\dist\bin\aether.exe --version
```

Expect roughly 60 GB free and one to three hours of compilation. The build
leaves two things in `obj-aether/dist`: the portable zip and
`AetherfoxSetup-<version>.exe`.

## Verifying a build is Aether

Useful if you built this yourself, or want to check someone else's binary.

- *About Aetherfox* shows the Aetherfox wordmark and the version, not Firefox.
- `about:aethersettings` is the settings page; stock `about:preferences`
  is on its way out.
- `about:telemetry` shows no active upload configuration.
- Sync and the account button are absent from the toolbar and the menu.
- No `about:policies` banner: Aetherfox ships no enterprise policies.

## License

[MPL-2.0](LICENSE), matching upstream Firefox. The patches in this repository
are original work and are offered under the same terms. See
[LICENSING.md](LICENSING.md) for details.
