# Aetherfox 0.1 — changelog

First release. Firefox 156.0.1 with telemetry, Sync/FxA and several Mozilla
subsystems removed, shipped as a public patch stack so the whole delta against
upstream can be audited without trusting a binary.

The stack holds 20 thematic groups (squash of the 171-unit history). Each
group file carries the headers of its member units, so nothing of the
history is lost; the per-unit backup lives outside the repo.

---

## 01. Aether: base product

Branding, prefs, update channel, about pages: the Aether product shell.

Squashed from 1 units: 01-product.

## 02. Aether: Sync/FxA wiped

Sync, Firefox Accounts and account UI removed from build and UI.

Squashed from 1 units: 02-sync-wipe.

## 03. Aether: telemetry killed

The telemetry removal across core, features, toolkit, DOM, media, gfx, urlbar, search, tabbrowser, YAML packs and pings.

Squashed from 24 units: 03-telemetry-core, 04-telemetry-feat-a, 05-telemetry-feat-b, 06-telemetry-tail, 07-glean-buildfix, 08-js-leftovers, 09-network, 10-platform-buildfix, 12-toolkit, 13-dom, 14-image, 15-security, 16-window-race, 17-devtools-watchrace, 18-gfx-telemetry, 20-core-telemetry, 21-urlbar-telemetry, 22-search-telemetry, 23-tabbrowser-telemetry, 24-yaml-pack1, 25-yaml-pack2, 26-pings-browser-dom, 27-pings-toolkit, 28-update-telemetry.

## 04. Aether: final telemetry sweep

Optional Features section, dead pings, gecko-trace out, last Glean writers, final sweep, and the offline stub foundation.

Squashed from 6 units: 29-optional-features, 30-dead-pings, 31-no-gecko-trace, 32-stub-offline, 33-last-glean-writers, 34-final-cleanup-sweep.

## 05. Aether: installer UX

Offline NSIS stub flow, welcome gate, splash, modern UI, setup icon.

Squashed from 1 units: 35-installer-ux.

## 06. Aether: dead callsites, part A

ExtensionTelemetry, Nimbus, autofill, startup, BrowserUsage, WebRTC emitter, telemetry events, translations, usage calls, AboutWelcome.

Squashed from 14 units: 36-dead-exttelemetry-calls, 37-dead-nimbus-calls, 38-dead-autofill-calls, 39-dead-startup-module, 40-dead-btu-calls, 41-webrtc-no-emitter, 42-dead-telemetry-events, 43-translations-telemetry-sink, 44-dead-usage-calls-1, 45-dead-aboutwelcome-calls, 46-dead-newtab-doh-calls, 47-dead-search-calls, 48-dead-usage-calls-2, 49-legacy-callsites.

## 07. Aether: telemetry backends out

Extension telemetry API, payload flows, ASRouter, client env, targeting, clientID, environment readers, reporting policy, experiment mirror, restored backends, util readers, backend JS, orphan enums.

Squashed from 14 units: 50-ext-telemetry-api, 51-dead-payload-flows, 52-asrouter-telemetry-flow, 53-clientenv-teleportals, 54-targeting-attrs, 55-dead-clientid-import, 56-clientid-replacement, 57-environment-readers, 58-reporting-policy, 59-experiment-env-mirror, 60-restore-backend-modules, 61-util-readers, 62-backend-js, 63-orphan-enum-includes.

## 08. Aether: webrtc/search tail

Third-party relocation, WebRTC using declarations, search detection, backend C++, l10n handler, Nimbus/Mach/WebRTC telemetry.

Squashed from 8 units: 64-thirdparty-relocation, 65-webrtc-using, 66-search-detection-perm, 67-backend-cpp, 68-l10n-onchange-handler, 69-nimbus-telemetry, 70-mach-telemetry, 71-webrtc-telemetry.

## 09. Aether: ads and Pocket out

GIFFT bridge, MaRS ads, Pocket data and rest, manual updates, viaduct/necko, crash ping, GIFFT leftovers.

Squashed from 8 units: 72-gifft-bridge, 73-mars-ads, 74-pocket-data, 75-pocket-rest, 76-manual-updates, 77-viaduct-necko, 78-crash-ping, 79-gifft-leftovers.

## 10. Aether: newtab/search/suggest cleanup

Newtab orphans and dead content, local search, topsites, Firefox Suggest, Merino, crossword, search telemetry, suggest items, urlbar engagement, provider dispatch, group labels, FOG about:glean, sponsor protection, data-submission infobar, leftover metrics, top-window hardening, AI window, login migration, addon tab notes, sponsored attribution.

Squashed from 22 units: 80-newtab-orphan-tests, 81-newtab-dead-content, 82-newtab-local-search, 83-newtab-search-corners, 84-no-sponsored-topsites, 85-no-firefox-suggest, 86-no-merino-widgets, 87-no-crossword-attribution, 88-no-search-telemetry, 89-no-empty-suggest-item, 90-no-urlbar-engagement-telemetry, 91-restore-provider-engagement-dispatch, 92-no-suggest-group-label, 93-no-fog-about-glean, 94-no-sponsor-protection, 95-no-data-submission-infobar, 96-no-record-glean-metrics-leftover, 97-harden-top-non-pb-window, 98-no-aiwindow-telemetry-shells, 99-no-login-migration-pwmgr-telemetry, 100-no-usage-addon-tabnotes-telemetry, 101-no-sponsored-attribution-thirdparty-leftovers.

## 11. Aether: Glean DOM bindings and docs out

Glean WebIDL bindings and metric layer, telemetry docs trees, extension Glean global.

Squashed from 3 units: 102-no-glean-dom-bindings, 103-no-telemetry-docs, 104-no-extension-glean-global.

## 12. Aether: accounts and Normandy out

Firefox Accounts UI, sync promos and widgets, Normandy and its newtab fallout.

Squashed from 4 units: 105-no-firefox-accounts, 106-no-sync-promos-widgets, 107-no-normandy, 108-no-normandy-newtab-fallout.

## 13. Aether: fingerprinting core

RFP off by default, signal registry, canvas/WebGL/audio noise, core count, text metrics, master switch, audiobuffer noise, per-site exceptions, UA compat token, worker cores.

Squashed from 13 units: 109-disable-rfp-by-default, 110-fingerprinting-signal-registry, 111-canvas-noise-2d-reads, 112-canvas-noise-encode-paths, 113-webgl-noise-reads, 114-webaudio-analyser-noise, 115-normalize-hardware-concurrency, 116-canvas-text-metrics-nudge, 117-fingerprinting-master-switch, 118-audiobuffer-channel-noise, 119-per-site-fingerprint-exceptions, 120-firefox-ua-compat-token, 121-worker-hardware-concurrency.

## 14. Aether: protection panels and layers

Shields panel, trust reroute, known-fingerprinter blocking, stock UA, top-load keying, GL baselines, touch/fonts/language/depth/timezone normalization.

Squashed from 11 units: 122-aether-shields-panel, 123-trust-panel-reroute, 124-block-known-fingerprinters, 125-stock-firefox-ua, 126-top-load-keying, 127-gl-caps-baseline, 128-normalize-touch-points, 129-restrict-page-fonts, 130-single-page-language, 131-stock-screen-depth, 132-utc-timezone-optin.

## 15. Aether: the new settings page

Redesign toggles, fine-grained switches, standalone skeleton, button reroute, design switch, media/gamepad/motion shields, samplerate, intl coherence, battery/connection absences, geometry layer, standard/strict split, copy and presets, standard defaults, profile radios.

Squashed from 17 units: 133-settings-redesign-toggles, 134-fine-grained-switches, 135-standalone-settings-skeleton, 136-settings-button-reroute, 137-interface-design-switch, 138-media-device-shield, 139-gamepad-normalization, 140-motion-sensor-shield, 141-normalize-audio-samplerate, 142-intl-coherence, 143-record-battery-absence, 144-record-connection-absence, 145-geometry-strict-layer, 146-standard-strict-split, 147-settings-copy-and-presets, 148-standard-defaults, 149-profile-radios.

## 16. Aether: native blocker engine

Bundled uBlock removed, engine core, snapshot lists, CNAME wiring, updates settings, cosmetic filtering, redirect surrogates, has/selectors, has-text, scriptlets, fingerprint blocking in Standard, parity phase A, list catalog.

Squashed from 13 units: 150-remove-bundled-ublock, 151-blocker-engine-core, 152-blocker-snapshot-lists, 153-blocker-wiring-cname, 154-blocker-updates-settings, 155-blocker-cosmetic, 156-blocker-redirect-surrogates, 157-blocker-has-selectors, 158-blocker-has-text, 159-blocker-scriptlets, 160-fingerprint-blocking-in-standard, 161-ublock-parity-phase-a, 162-ublock-list-catalog.

## 17. Aether: adblock sections

Own Ad blocking section, site panel, blocked count, list layout, master switch, master and custom lists, fingerprint copy and Strict opt-ins.

Squashed from 7 units: 163-adblock-own-section, 164-panel-site-adblock, 165-shield-blocked-count, 166-adblock-list-layout, 167-adblock-master-switch, 168-adblock-master-and-custom-lists, 169-fingerprint-copy-and-strict-optins.

## 18. Aether: adblock and settings polish

Filter-list update modes, design-switch removal from the new page, per-list update status, subhead hierarchy.

Squashed from 4 units: 171-list-update-modes, 174-no-design-switch, 175-list-update-status, 176-subhead-hierarchy.

## 19. Website moves to GitHub Pages

No aether.browser domain: help/feedback links, installer defines,
release-notes/homepage/update-manual prefs and the report-site
placeholder now point at the Pages site
(https://aethergroup.github.io/aether, same paths). Theme add-on IDs
are identifiers, not links, and stay untouched.

## 20. Aether: manual-only updates

Updates are user-driven, enforced in the code: no startup check, no automatic
download, no policy hooks. The user starts the search, the user starts the
download, the user restarts.
