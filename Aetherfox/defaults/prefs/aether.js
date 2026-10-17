// Aetherfox - defaults/prefs/aetherfox.js v1
// Minimal Arkenfox-flavoured base, no Rust/C++ touched. Prefs + policies only.
// These prefs are carried into the tree by the branding/01-product patch on top
// of browser/app/profile/firefox.js (or whatever the equivalent is per version).

// --- Telemetry / Data Reporting OFF ---
pref("toolkit.telemetry.unified", false);
pref("toolkit.telemetry.enabled", false);
pref("toolkit.telemetry.archive.enabled", false);
pref("toolkit.telemetry.bhrPing.enabled", false);
pref("toolkit.telemetry.firstShutdownPing.enabled", false);
pref("toolkit.telemetry.newProfilePing.enabled", false);
pref("toolkit.telemetry.shutdownPingSender.enabled", false);
pref("toolkit.telemetry.updatePing.enabled", false);
pref("toolkit.telemetry.server", "");
pref("datareporting.healthreport.service.enabled", false);
pref("datareporting.healthreport.uploadEnabled", false);
pref("datareporting.policy.dataSubmissionEnabled", false);
pref("datareporting.usage.uploadEnabled", false);
pref("browser.ping-centre.telemetry", false);

// --- Normandy / Shield / Studies OFF ---
pref("app.normandy.enabled", false);
pref("app.normandy.api_url", "");
pref("app.shield.optoutstudies.enabled", false);
pref("experiments.enabled", false);
pref("experiments.manifest.uri", "");

// --- Pocket / Sponsored / Bloat OFF ---
pref("extensions.pocket.enabled", false);
pref("browser.newtabpage.activity-stream.feeds.telemetry", false);
pref("browser.newtabpage.activity-stream.telemetry", false);
pref("browser.newtabpage.activity-stream.showSponsored", false);
pref("browser.newtabpage.activity-stream.showSponsoredTopSites", false);
pref("browser.newtabpage.activity-stream.feeds.section.topstories", false);
pref("browser.messaging-system.whatsNewPanel.enabled", false);

// --- Network services pointed at a dummy (Helium's Dummy URL approach) ---
pref("toolkit.telemetry.cachedClientId", "");
pref("network.captive-portal-service.enabled", false);
pref("network.connectivity-service.enabled", false);
pref("browser.region.network.url", "");
pref("browser.region.update.url", "");
pref("extensions.update.enabled", false);
pref("extensions.getAddons.cache.enabled", false);

// NOTE v1: app.update.url and safebrowsing are handled in
// patches/core/01-product.patch. Do not break SafeBrowsing without our own
// proxy (see aether-services in v2).

// --- Security / Privacy ON ---
pref("dom.security.https_only_mode", true);
pref("privacy.resistFingerprinting", true);
pref("privacy.fingerprintingProtection", true);
pref("privacy.trackingprotection.enabled", true);
pref("privacy.trackingprotection.pbmode.enabled", true);
pref("media.peerconnection.enabled", false);
pref("webgl.disabled", false);

// --- Minimal Aetherfox UX ---
pref("browser.rights.3.shown", true);
pref("browser.shell.checkDefaultBrowser", false);
pref("startup.homepage_welcome_url", "");
pref("startup.homepage_override_url", "");
pref("browser.startup.homepage", "about:blank");

// --- Aetherfox Services (opt-in, see patches/core/01-product.patch) ---
pref("services.aether.enabled", false);
pref("services.aether.origin", "");
pref("services.aether.schemaVersion", 1);
