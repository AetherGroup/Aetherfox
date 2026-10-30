# Licensing

## This repository

The patches, branding, defaults and scripts in this repository are original
work and are released under the [Mozilla Public License 2.0](LICENSE).

## Firefox

Aetherfox is built from `mozilla-firefox/firefox`, pinned to the tag in
`firefox_version.txt`. That source is fetched at build time and is not part
of this repository. Firefox is also MPL-2.0, so the resulting binaries are
covered by the same license.

Under MPL-2.0 you may use, modify and redistribute these files, including
in larger works, provided any modified files remain available under MPL-2.0
with their source.

## Bundled third-party components

No browser extension and no filter list is bundled. The offline setup packs
two OFL fonts (Quicksand and Comfortaa) and the 7-Zip SFX stub; each keeps
its own license, and none of them is committed here.