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

### uBlock Origin

The uBlock Origin XPI bundled in builds is fetched unmodified from
[gorhill/uBlock](https://github.com/gorhill/uBlock) releases and is signed
by Mozilla. It keeps its own license; see the upstream repository.

The XPI itself is not committed here. `aether.deps.ini` records the pinned
version and the download URL.