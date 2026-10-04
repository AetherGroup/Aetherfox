# AGENTS.md — Aether Browser operations manual

This repo is a **patch-built soft-fork of Firefox**. Everything you need to
build it from scratch and to keep working on it is here. If you are coming in
without memory, read the whole thing before touching anything.

---

## 1. What this is, in 30 seconds

- Firefox **156.0.1** (`FIREFOX_156_0_1_RELEASE`, base commit
  `19a90052d7869f7b194ff27d316520366ad1d592`) with telemetry, Sync/FxA and
  several Mozilla subsystems removed.
- The code **is not edited here**: the source of truth is **18 thematic patch
  groups** in `patches/core/`, applied in the order given by `patches/series`
  (squash of the 171-unit history; each group file carries its member headers,
  per-unit backup outside the repo).
- The **working tree** (`../firefox-src` by default) is a *derivative*: you get
  it by applying the stack to a clean Firefox checkout.
- The patches are **public on purpose**: the project ships as patches so that
  anyone can audit exactly what changed relative to Mozilla.

### Repo topology

```
patches/series            application order (18 patches)
patches/core/NN-*.patch   the patches; one file can be touched by several
branding/                 29 brand assets (canonical source; kept OUT of git)
third_party/               third-party downloads (git-ignored; retired: uBlock)
scripts/sync.py           toolchains + clone/verify/apply the stack + branding
scripts/build.py          build/package wrapper (mach build + mach package)
scripts/make-stub-offline.py  packs stub + full installer into the shipped setup exe
scripts/verify-flags.py   post-build privacy check (exits != 0 on failure)
scripts/regen-patch.py    regenerates a patch from the working tree
scripts/rebase.py         builds a throwaway repo with one commit per patch
scripts/make-mar-local.py generates the (unsigned) partial-update MAR
scripts/aus-local.py      local update server with buildID comparison
scripts/generate-icons.py regenerates the brand icons
scripts/generate-fonts.py  builds the installer's WOFF fonts from the
                  variable sources (needs fontTools + brotli)
scripts/patch-sfx-stub.py patches the installer's SFX stub
docs/BUILD.md             build guide
mozconfig.windows         build configuration (Windows x64, aether-release channel)
firefox_version.txt       the Firefox tag the stack targets
aether.deps.ini           third-party downloads (all retired since 150)
```

---

## 2. Getting started from scratch

### 2.1 Requirements to install (this part CANNOT be automated)

| What | Detail |
|---|---|
| Windows 10/11 x64 | tested on Windows 11 IoT Enterprise LTSC 26100 |
| Visual Studio Build Tools 2022 | **Desktop development with C++** workload + Windows SDK 10/11 |
| MozillaBuild | the shell with the toolchains; `start-shell.bat` |
| Python 3.12 or 3.13 | with 3.13 mach warns: *"higher than the highest known working version"*. It works, but if you see oddities use 3.12 |
| Git | with long-path support |
| ~60 GB free | the Firefox tree takes ~23 GB and the objdir ~15 GB |

**No .NET SDK is required.** `installer/` holds an abandoned .NET/Avalonia
installer that nothing builds or ships; `build.py` no longer touches it. Keep it
in the tree for the record, ignore it completely.

`mach bootstrap` installs **only Rust** (~20 min, including `mach`'s venvs).
The real toolchains (clang-cl, WASI sysroot, WinAppSDK, windows-rs, nasm, node,
NSIS) are **not installed on Windows**, and `docs/BUILD.md` explains why: on a
release tag `--enable-bootstrap` only defaults to on in nightly. `sync.py`
downloads them in its `ensure_toolchains` step, before removing `mobile/` and
before applying the stack. Do not assume they are there: if you change the
order in `sync.py`, configure dies with `Cannot find the target C compiler`.

### 2.2 ⚠️ The FIREFOX TREE goes in a SHORT path (the repo can live anywhere)

Two different problems, do not confuse them:

- **`git clone`**: the checkout has files longer than **MAX_PATH** (test262).
  On long paths `git checkout` fails with `Filename too long`. Fixed with
  `core.longpaths=true`.
- **The build**: past a certain absolute-path length mozmake stops seeing its
  inputs and the `libxul` link fails with `No rule to make target` **pretending
  a file is missing**. `core.longpaths` does not fix this. **It is not our
  problem**: upstream's `configure.py` carries `WIN32_MAX_PATH = 260` and
  `LONGEST_KNOWN_OBJDIR_RELATIVE_PATH = 170`, which works out to a **62-char
  limit for the srcdir**, and its recommended layout is
  `D:\mozilla-source\firefox` (26 chars). We are at 8. The full chain (GNU make
  bug 58656 and Mozilla bug 1712350, which their CI hit) is in
  `docs/BUILD.md`. Measured on the real tree:

  | worktree path | longest path | files ≥ 224 chars |
  |---|---|---|
  | `C:\Users\Someone\Documents\firefox-src` | 253 | 195 |
  | `C:\o\fs` | 222 | **0** |

  The worktree has to be genuinely short. **The repo may live in `Documents`**:
  the wrappers derive their paths from their own location and the repo length
  never enters the link. What compiles is `firefox-src`.

- **The budget is 8 prefix characters**, and that forces a short worktree name.
  Any path ending in `\firefox-src\` is unworkable by construction: the name
  alone eats the margin.

  What counts is not the longest path in the tree but the longest path the
  build **touches**. The test262 fixtures reach 214 chars but they are test
  data and never enter the graph (this build walks `testing/web-platform` and
  stops there). The build's outputs top out at **170 chars relative to the
  objdir**, exactly upstream's `LONGEST_KNOWN_OBJDIR_RELATIVE_PATH` constant.
  Measured on the real tree, skipping test data:

  | worktree | prefix | relevant path | margin |
  |---|---|---|---|
  | `C:\aether-156\` | 14 | 190 | 33 |
  | `D:\mozilla-source\firefox\` | 26 | 202 | 21 |

  Upstream allows 62 chars of srcdir, so there is plenty of room: **use a name
  that means something**, `C:\aether-156`, and `C:\aether-157` on the rebase.
  Renaming **costs nothing**: a rebase changes thousands of files, so the objdir
  has to be rebuilt anyway.

  **`sync.py` measures this and fails there** (`check_path_budget`, skippable
  with `--skip-path-check`). It measures the longest path in the freshly cloned
  tree and, if it goes over 223, says exactly how many characters you are over,
  instead of letting the `libxul` link blow up 40 minutes later. Do not skip it:
  it is the difference between an error that tells you the fix and a lost
  afternoon.

  That is why `_env.cmd` accepts `FIREFOX_SRC`: the wrappers defaulted to
  `..\firefox-src`, which with a short root can **never** work. Without that
  override you have to invoke `mach` by hand.

### 2.3 Exact execution order

```powershell
# 0. cd into the repo. If the worktree is elsewhere, pass it with --src
cd C:\dev\aether-browser

# 1. (removed since 150: no bundled extensions to download; blocking is
#    native now. third_party/ stays git-ignored for future retired deps.)

# 2. Clone Firefox at the exact tag in firefox_version.txt
git clone --branch FIREFOX_156_0_1_RELEASE --depth 1 `
  https://github.com/mozilla-firefox/firefox.git C:\fs

# 3. Apply the stack. Before touching the tree, download the toolchains that
#    `mach bootstrap` does NOT install on Windows (clang-cl, WASI sysroot,
#    WinAppSDK, windows-rs): the taskgraph resolves them and for that it still
#    needs mobile/ in place. Then remove mobile/, apply the patch stack and
#    copy branding (no staged binaries since 150).
#    --skip-toolchains if the machine is already set up or there is no network.
python scripts\sync.py --src C:\fs --apply --no-download
#    Expected: "toolchains: already installed in ..." or the download
#              "98 applied, 0 already there, 0 in conflict"
#              "branding assets: 54 gaps filled from unofficial, 28 Aether files"
#              "distribution: carried by the series (no staged binaries)"

# 4. Build + package
$env:MOZCONFIG="C:\dev\aether-browser\mozconfig.windows"
$env:MOZ_APP_NAME="aether"
$env:MAR_CHANNEL_ID="aether-release"
$env:ACCEPTED_MAR_CHANNEL_IDS="aether-release"
python scripts\build.py --src C:\fs

# 5. Privacy check on the result
python scripts\verify-flags.py --objdir C:\fs\obj-aether
#    Expected: TODO OK and exit code 0

# 6. (optional) MAR + local update server
python scripts\make-mar-local.py --srcdir C:\fs\obj-aether\dist\aether --channel aether-release
python scripts\aus-local.py --dir <mar-folder> --mar aether-156.0.1.complete.mar --port 8000
```

Expected output of `build.py` in `obj-aether/dist/`:

| File | Produced by |
|---|---|
| `aether-156.0.1.en-US.win64.zip` | `mach package` (the payload) |
| `aether-156.0.1.en-US.win64.installer.exe` | `mach package` (the full NSIS installer) |
| `setup-stub.exe` | `mach package`, because `MOZ_STUB_INSTALLER=1` in the mozconfig |

**The shipped setup is assembled by `build.py` itself**, not manually: after
`mach package` it runs `make-stub-offline.py`, which writes
`obj-aether/dist/AetherSetup-<version>.exe` (~93 MB): the 7z SFX stub
plus a payload holding both `setup-stub.exe` and the full installer, so it
installs with no network. Check it with `7zr l`. Then `build.py` deletes
the standalone installers from dist (the bare stub would download from
Mozilla; the full one is redundant once packed) — dist ships only
AetherSetup, the zip and small metadata.

**Naming trap.** `AetherSetup-*.exe` used to be the .NET installer and is now the
NSIS stub: same name, completely different artifact (~93 MB offline NSIS against
the old ~299 MB .NET one). `installer/` still holds those .NET sources; they are
dead and nothing builds them.

`build.py` also **fails** if `uninstall/helper.exe` is missing from the package
(`assert_uninstaller_ships`): the browser could then not be removed after an
update.

### 2.4 Smoke test

```powershell
C:\fs\obj-aether\dist\aether\aether.exe --version
# Must print:  Aether Aether 156.0.1
```

---

## 3. The mental model: patches as the source of truth

This is the part that confuses newcomers most.

```
   patches/series + patches/core/*.patch     <- THE SOURCE OF TRUTH
                    |
                    |  scripts/sync.py --apply
                    v
        ../firefox-src  (working tree)      <- derived, gets regenerated
                    |
                    |  you edit here
                    v
              scripts/regen-patch.py        <- dumps the change into the patch
```

**Golden rule:** always edit the real file in `firefox-src` and then regenerate
the patch. Never hand-edit a patch to add code (you may hand-edit header text
or nudge an individual hunk).

The correct cycle for a change:

1. Edit the real file in `firefox-src`.
2. Regenerate that patch's section.
3. Verify (section 5).
4. Commit in this repo.

---

## 4. How telemetry gets removed (the most repeated task)

### 4.1 Where everything lives

| What | Where |
|---|---|
| Ping definitions | `toolkit/components/glean/pings.yaml` |
| Metric definitions | `<module>/metrics.yaml` (many modules) |
| Metric index | `toolkit/components/glean/metrics_index.py` (generated) |
| Ping timers | ` glean::…Ping` classes in each module |
| Writers | `.Record()`, `.Accumulate()`, `.EnumGet()`, `.Add()` calls |
| Histograms | `StaticHistogram` and friends |
| Crash annotations | `CrashReporter::AnnotateCrashReason` and similar |
| Telemetry asserts | `MOZ_ASSERT(…, "…")` that check metrics |

### 4.2 Procedure per work group

1. **Locate** the ping or metric: search its name in `pings.yaml`,
   `metrics.yaml` and its uses (`git grep`).
2. **Delete the definition** from the matching YAML.
3. **Delete every use**: writers, timers, asserts and crash annotations.
   Leave the hook if the rest of the function is still used; if the function
   ends up empty it can be deleted whole, but check nothing still calls it.
4. **Remove the `#include`s or `using`s** that are now unused.
5. **If you touched a `metrics.yaml`**, make sure `metrics_index.py` is still
   coherent: the build fails if it is not. It is a generated file; if needed,
   regenerate it with whatever mechanism the module uses (check its `moz.build`).
6. **Replicate the change in the thematic patch that owns that area.** Patch map
   by area:

   | Patch | Area |
   |---|---|
   | `01-product` | branding, about:dialog, prefs, Setup, OTR, distribution |
   | `02-sync-wipe` | Sync/FxA, OTR, module moz.build files |
   | `03`–`06`, `20`, `26`, `27` | telemetry in blocks (core, features, toolkit) |
   | `07`, `08` | Glean build, leftover JS |
   | `09` | netwerk |
   | `10` | platform, base telemetry, build prefs |
   | `12` | toolkit |
   | `13`–`16` | dom, image, security, window race |
   | `17` | devtools |
   | `18` | gfx |
   | `21`–`23` | urlbar, search, tabbrowser |
   | `24`–`25` | metrics YAML |
   | `28` | updates |
   | `29` | Optional Features (opt-in features) |
   | `30` | dead pings |
   | `31` | gecko-trace and OpenTelemetry (whole components) |
   | `32` | Firefox installer removed; only the uninstaller is left |

   A change usually touches several patches in the same group. **Regenerate from
   the highest number down to the lowest** (see 4.4).

7. **Verify** (section 5). No commit without verification.

### 4.3 Regenerating a patch

The simple case (a single patch owns the file):

```powershell
python scripts\regen-patch.py `
  --repo C:\fs `
  --base 19a90052d7869f7b194ff27d316520366ad1d592 `
  --patch patches\core\13-dom.patch `
  --files dom/media/CubebUtils.cpp `
  --from-worktree
```

`--from-worktree` runs `git diff <base> -- <files>`: it dumps the tree's current
state into the patch. By default (without the flag) it uses `base..HEAD` of a
rebase repo.

### 4.4 ⚠️ When several patches touch the same file

This is the normal case, not the exception (e.g. `AboutRedirector.cpp` is in
`01` and `03`). Here `regen-patch.py` is **not enough**: `--from-worktree` would
generate the base→final-state diff, which is wrong for an intermediate patch,
because the later patches would stop applying.

There are two routes:

**Recommended route: `scripts/rebase.py`** — builds a throwaway repo with one
commit per applied patch. There each patch is a real commit and
`regen-patch.py` with `base..HEAD` works unambiguously, patch by patch, from the
bottom up.

**Direct route:** for each affected patch, from **the highest number to the
lowest**, replace its section of the file with the diff between "tree with the
earlier patches applied" and "tree with this patch applied". That is exactly
what a post-process does: apply the later patches as the post-image, then
extract the file's diff. Few lines, but it is a script; if you write it,
**verify afterwards with the full tree comparison** (section 5).

### 4.5 ⚠️ Do not blindly regenerate the whole stack

A massive `regen` rewrites sections that look redundant and **deletes files
that are no longer in their patch**. The patch still applies, the "applies
cleanly" check still goes green, and the clean clone ends up with upstream's
file. **This has already happened**: `netwerk/protocol/http/HttpBaseChannel.h`
was in no patch at all and broke the build on a clean clone while the working
tree compiled fine.

Regenerate only the files you touched, and always cross-check with the full
tree comparison.

---

## 5. Verification: five gates, all mandatory before committing

| # | What it checks | How |
|---|---|---|
| 1 | The series applies on the base | `python scripts/sync.py --apply` → "98 applied, 0 in conflict" |
| 2 | **The stack rebuilds the whole tree** | clean clone test (below) |
| 3 | Build privacy defaults | `python scripts/verify-flags.py --objdir ...` → "TODO OK" |
| 4 | It compiles and packages | `python scripts/build.py` → rc 0 |
| 5 | The binary runs | `aether.exe --version` → "Aether Aether 156.0.1" |

### 5.1 The clean clone test (the gate that actually matters)

Gate 1 is **structurally blind**: it only checks whether the patch fits what is
in front of it. If a file falls out of the stack, nobody notices. Gate 2
compares the **whole tree** and is the only one that catches it.

```powershell
# Clean clone at the base commit (SHORT path, for MAX_PATH)
git clone --shared --no-checkout C:\fs C:\cr\t
git -C C:\cr\t checkout -f 19a90052d7869f7b194ff27d316520366ad1d592

# Exactly the path a new user would use
python scripts\sync.py --src C:\cr\t --apply --no-download
```

Then compare the two trees: in each, `git status --porcelain
--untracked-files=all` gives you the list of touched files; they must match
**and** the contents must be identical byte for byte. Files deleted in both are
fine.

What it should give (measured on `FIREFOX_156_0_1_RELEASE` + group 32):
**17,469** files touched in both, 0 exclusive to one side, 0 differing
contents. Of those 17,469, **15,019 are the `mobile/` removal** that `sync.py`
does; the stack itself is **2,450** (1,059 deleted + 1,314 modified + 77 new).
If you compare against a tree where `mobile/` is still present, exclude it or
the count will not add up.

> `git clone --shared` reuses the original repo's objects: it clones in seconds
> without downloading 5 GB. `core.longpaths=true` if the path is long.

### 5.2 If the change only touches comments

Check that the diff **contains no lines of code**. Pull out the `+`/`-` lines
from the patch that are not comments (`//`, `#`, `*`, `<!--`) and not `@@`
headers: there should be none.

---

## 6. The updater

- **Channel:** `aether-release`. Pinned in `mozconfig.windows` with
  `--with-update-channel`, `MAR_CHANNEL_ID` and `ACCEPTED_MAR_CHANNEL_IDS`.
  The last one is what makes the updater accept a MAR that is not from a
  Mozilla channel.
- **Unsigned MAR** (`--enable-unverified-updates`). Official MARs are signed;
  without a signature, development builds only.
- **A MAR** is a partial update: ~93 MB instead of the ~130 MB of a full build.
  Generated by `scripts/make-mar-local.py`.
- **`scripts/aus-local.py` exists for a concrete reason**: `mach update serve`
  always advertises a fake future buildID, so the browser offered the same
  update on every startup. This server compares the `BUILD_ID` the client sends
  with the MAR's (sidecar `.buildid` file) and replies `<updates></updates>` if
  it is already up to date.
  **`policies.json` must carry the URL with `%VERSION%` and `%BUILD_ID%`**; with
  a static URL the server deliberately replies empty so it does not re-offer in
  a loop.
- Related prefs in `mozconfig.windows` / branding:
  `app.update.url.manual`, `app.update.url.details` (to the Pages site,
  `https://aethergroup.github.io/aether`),
  `app.update.interval` 86400, `app.update.promptWaitTime` 86400,
  `app.update.checkInstallTime.days` 2.

---

## 7. Publishing

- **Remote configured, nothing pushed yet.** `origin` =
  `https://github.com/AetherGroup/Aether-Browser.git` (public, still empty). No
  push until the tree and the stack have been reviewed.
- `.git` weighs ~12 MB: comfortably within GitHub's 100 MB per-file limit.
- **GitHub's limit is the reason `mobile/` is not in the stack** (see §8.3).
  GitHub warns at 50 MiB and **blocks at 100 MiB per file**: a patch cannot go
  over that. Any diff that deletes code in bulk (a massive `--without-wasm`, or
  removing `services/sync` entirely) hits that ceiling. Before publishing,
  actually check:

  ```powershell
  git ls-files | ForEach-Object { $i = Get-Item $_; [PSCustomObject]@{MB=[math]::Round($i.Length/1MB,1); F=$_} } |
    Sort-Object MB -Descending | Select-Object -First 10
  ```

  Today the largest file in the repo is `patches/core/02-sync-wipe.patch`
  (3.6 MB), with the rest of the stack under 2.1 MB. If a patch approaches
  50 MB, it needs rethinking, not uploading.
- If you ever have to rewrite history with `git filter-repo`, do it **with a
  clean tree**: work was lost once by running it with uncommitted changes.
- The website lives in `AetherGroup/aether` and is served with GitHub Pages
  (no `aether.browser` domain anywhere: help/feedback links, installer
  defines, release-notes/homepage/update prefs and the report-site
  placeholder all point at the Pages site).
- The installer does not go in the repo; it is distributed as a GitHub release.

---

## 8. Known traps (the ones that bit us)

1. **`mach lint` does not start.** `python/sites/lint.txt` pins `rumdl==0.1.91`,
   and that version **no longer exists on PyPI** (deleted, not just *yanked*;
   the API returns 404). Workaround used: repackage 0.1.96 as 0.1.91 and expose
   it with `PIP_FIND_LINKS` (`aether-tools/rumdlwheel/dist/` on the dev
   machine). Clean alternative: update the pin.
2. **`sync.py` copies `branding/` AFTER applying the patches.** If the repo and
   the patch disagree about the same file, the repo wins. `branding/` files and
   their patch sections must always match.
3. **`mobile/` is not in the stack, and not by choice.** `sync.py` removes it
   before applying. Encoding 15,018 deletions as a diff took **127 MB**, over
   GitHub's hard 100 MiB per-file limit: with the removal in the stack the repo
   **could not be published**, which is the whole point of this project. That
   is the definitive reason, not performance. The build is Windows-only and
   nothing under `mobile/` compiles or ships (audited: comments only,
   `desktop=false` branches and string tables). Consequence: "the patches are
   the source of truth" has one exception, and gate 2 is the net under it.
4. **`git apply` needs `-c core.autocrlf=false`.** `sync.py` already passes it;
   if you apply patches by hand, pass it yourself.
5. **MAX_PATH.** See 2.2.
6. **There is no `node_modules`**, so `eslint`/`prettier` are unavailable
   without `npm install`. For C++ `mach lint --linter clang-format` is enough;
   it does not need node.
7. **Python 3.13** works but mach warns that it exceeds the known version.
8. **`branding/aether/dsstore`** is junk: a macOS `.DS_Store` that came in when
   copying from `unofficial/`. Harmless, still to be deleted.
9. **The comment cleanup left orphaned `*/` or duplicated braces** in a couple
   of files when merging blocks. The full tree comparison and a `clang-format`
   catch it; do not trust "applies cleanly" alone.
10. **`third_party/` is in `.gitignore`** (all deps retired since 150; the
    dir stays for future use).
11. **⚠️ On Windows the build uses clang-cl, not `cl.exe`.** Firefox 156
    compiles with the clang-cl in `~/.mozbuild/clang/bin` and only uses MSVC for
    headers and libs. That is why having `msvc140` installed is not enough:
    without clang-cl, `mach configure` dies with
    `Cannot find the target C compiler`.
12. **⚠️ The taskgraph that downloads the toolchains hashes files that Aether
    removes.** Run on an already-modified tree it fails with
    `FileNotFoundError: ... mobile/android/android-components/build.gradle` or
    with `... toolkit/crashreporter/test/browser/browser_aboutCrashesResubmit.js`.
    That is why `sync.py` downloads them **before** removing `mobile/` and
    before applying the stack, and why the step passes
    `--enable-bootstrap=no-update` (idempotent). Never move that step after the
    `mobile/` removal.
13. **⚠️ Paths over ~224 chars break the `libxul` link.** mozmake stops seeing
    its inputs and you get `No rule to make target` pretending a file is
    missing. Measured: `Documents\firefox-src` → longest path 253 and 195 files
    ≥224; `C:\o\fs` → 222 and **0**. Always build from a short path, and do not
    confuse this error with a broken patch.
14. **`winget install NASM.NASM` installs nothing usable**: it says "Successfully
    installed", does not register the package and leaves no `nasm.exe`
    anywhere. Install it by hand into `C:\tools\nasm` (recipe in
    `docs/BUILD.md` §4).
15. **⚠️ NSIS is needed for the installer *and* the uninstaller.** Both are
    load-bearing. `mach package` builds `installer.nsi` (the full installer) and
    `setup-stub` (because `MOZ_STUB_INSTALLER=1`), and `uninstaller.nsi` produces
    `helper.exe`, which ships *inside* the browser as `uninstall/helper.exe`
    (added by `browser/installer/package-manifest.in` under
    `#ifdef HAVE_MAKENSISU`) and which the updater runs after every update.
    Drop NSIS from `ensure_toolchains`, or stop passing it
    `--enable-bootstrap`, and the packaging fails with "makensis not found" or
    "Missing file(s): bin/maintenanceservice_installer.exe", and the package can
    ship with no uninstaller: an installed Aether cannot be removed after an
    update. `build.py` fails if `uninstall/helper.exe` is missing.
    What *is* optional is MSI/MSIX, which this build never generates
    (`MOZ_PKG_FORMAT=ZIP`).
16. **A patch that deletes binary files needs the full sha in its `index`
    line.** `git apply` will not delete a `.png` with the abbreviated sha that
    plain `git diff` emits: it says `cannot apply binary patch ... without full
    index line`. Generate it with `git diff --full-index`. Also mind
    `Path.write_text()` / `open(..., 'w')` on Windows: they translate `\n` to
    CRLF and corrupt the whole patch, so write with `write_bytes()`. And
    Mozilla's `.md`/`.nsi` files are not cp1252, so `subprocess` with
    `text=True` blows up while decoding.
17. **A patch can apply cleanly and still be wrong.** `git apply --check`,
    `--reverse --check` and a numstat recount only prove the *diff* is valid,
    not that the result is. Cutting a makefile edit by line numbers produced a
    patch that applied perfectly and left `makensis.mk` with the
    `$(CONFIG_DIR)/helper.exe` rule header cut off its recipe, so the build died
    33 minutes in with `No rule to make target 'instgen/helper.exe', needed by
    'uninstaller'`. Edit makefiles by **content anchors**, and let make be the
    judge: a makefile is only validated by running the build.
18. **`sync.py`'s report can be wrong too.** "covered by a later patch" only
    looked at patches already known to be applied, so it never followed a chain
    and misreported `04-telemetry-feat-a` as a CONFLICT on a tree where it was
    perfectly applied. It is transitive now. When the report and reality
    disagree, gate 2 decides, not the log.
19. **The uninstaller and the maintenance service are load-bearing and easy to
    break.** `uninstall/helper.exe` is NSIS (`uninstaller.nsi`), built during
    `mach build` and run by the updater after every update. Nothing else in the
    build notices if it stops shipping: the zip packages fine and just has no
    way to remove Aether from a machine that was updated. `build.py` now fails
    if it is missing.
    `MOZ_MAINTENANCE_SERVICE` is **ON** in this build, and
    `maintenanceservice_installer.exe` is not just another artifact:
    `package-manifest.in` lists it, and `defines.nsi.in` hands
    `!define MOZ_MAINTENANCE_SERVICE` to NSIS, so `uninstaller_helpers.nsh` has a
    live branch that execs `maintenanceservice_installer.exe /Upgrade`. Deleting
    it fails the packaging with *"Missing file(s):
    bin/maintenanceservice_installer.exe"*, and if you also stripped the
    manifest entry you would ship an uninstaller that only breaks when the user
    uninstalls. It ships inside the browser package, not in `dist/`.
20. **⚠️ Check that the clean clone actually has the tree before trusting gate
    2.** A clone on a filesystem that does not record ownership (FAT32, some
    network drives) makes git refuse to work: `fatal: detected dubious
    ownership`. `git clone` still prints "Cloning into...", so the checkout
    silently does nothing and the clone ends up with a handful of files. Then
    `sync.py` reports the *first* patch as a CONFLICT with "No such file or
    directory" for files that plainly exist in Firefox, and gate 2 fails for a
    reason that has nothing to do with the patches. Fix without touching your
    global config, so it reaches the git calls inside `sync.py` too:

    ```powershell
    $env:GIT_CONFIG_COUNT="1"; $env:GIT_CONFIG_KEY_0="safe.directory"; $env:GIT_CONFIG_VALUE_0="*"
    ```

    And assert `git ls-files | Measure-Object` is > 100000 plus the presence of
    `browser/app/distribution/distribution.ini` before applying the stack.
    Keep the clone on NTFS; a 450k-file tree on FAT32 is asking for trouble.
21. **⚠️ On this machine PowerShell formats numbers in the es-ES locale, where
    `.` is the thousands separator.** So `{0:N1}` over a value of `1577.3`
    prints `1.577,3`, which reads as "1.58" at a glance. That is how a 1.54 TB
    free drive got mistaken for a 1.58 GB one, which sent a clean clone to
    another disk for no reason. Print sizes with the unit spelled out and the
    value unsuffixed (`"$($d.FreeSpace/1GB) GB"`), or in bytes, or use
    `InvariantCulture` for anything you have to compare against a threshold.
    Same for Python `locale`-aware formatting.

22. **⚠️ `>` in PowerShell 5.1 writes UTF-16, not bytes.** Redirecting a tool's
    output to a file with `git diff ... > file.patch` produces a file `git apply`
    refuses with `No valid patches in input`, and it is twice the size it should
    be. Let git write the file itself: `git diff --output=file.patch`. Same trap
    family as 16, different door.
23. **⚠️ In a patch stack, a `-` line is not necessarily upstream.** A later
    patch often removes what an earlier patch added (patch 03 deletes the
    `aether-changelog` entry patch 01 introduced). Any script that rewrites a
    stack must therefore be **series-aware**: a `-` or context line may only be
    rewritten when its exact text appears as a `+` line in an *earlier* patch of
    the series, otherwise it has to stay byte-identical or the patch stops
    applying. Renaming blind in both directions breaks the stack: rewrite a real
    upstream line and it no longer matches, or leave ours alone and it never
    matches either. The tell that the logic is right: the **first** patch of the
    series renames **zero** `-` lines (all of its removals are genuinely
    upstream) and the count grows with the patch number. Also note `sync.py`'s
    classifier leans on `git apply --reverse --check`, so a hunk whose `-` and
    `+` lines are identical reads as "applicable" rather than "applied".

24. **⚠️ What actually stops pings is `MOZILLA_OFFICIAL`, not
    `MOZ_TELEMETRY_REPORTING`.** Do not reason about the telemetry gate from
    `mozconfig`, you will get it wrong (this file did, and so did the person
    auditing it). The real chain is:

    ```
    not MOZILLA_OFFICIAL            toolkit/library/rust/gkrust-features.mozbuild
      -> gkrust feature glean_disable_upload
        -> glean/src/init/viaduct_uploader.rs
             return UploadResult::http_status(200)   # "faking success", no I/O
    ```

    `MOZ_TELEMETRY_REPORTING` is a *different* and much weaker thing: it defines
    two C++ macros that compile the legacy telemetry code out. With the macros
    off the prefs (`toolkit.telemetry.enabled`,
    `datareporting.usage.uploadEnabled`, the health report ones) can all be true
    and nothing would leave, because the uploader is inert. The prefs are a third
    layer, not the guarantee.

    `MOZILLA_OFFICIAL` was settable with a plain environment variable and 81
    files read it, so `MOZILLA_OFFICIAL=1` in the shell would have brought back
    both the macros and the real uploader. Patch 10 now pins `mozilla_official()`
    to `return False` in `build/moz.configure/init.configure`, which makes the
    variable irrelevant. All five consumers use it as a boolean, so `False` is
    equivalent to the `None` it used to be. **Do not restore `if official:
    return True`.**

    Two escape hatches survive in `viaduct_uploader.rs` and both are inert here:
    `telemetry.fog.test.localhost_port < 0` (static pref, default 0, sends to a
    local test server, the user's own choice) and an `X-Debug-ID` header (nothing
    in the tree sets one for release builds).

    `scripts/verify-flags.py` checks both halves of the chain, reading
    `gkrust-features.mozbuild` and `init.configure` from `--src` (default: the
    objdir's parent), so reverting the patch fails the gate instead of quietly
    reopening the channel.
25. **⚠️ A signature change needs a tree-wide caller search, not a
    file-local one.** Removing the runnable-name parameter from
    `RunnableDidRun`/`MaybeReportAccumulatedTime` compiled fine in
    `nsThread.cpp` and died 8 minutes into the build in
    `TaskController.cpp:1368`, the third caller nobody had grepped for. After
    changing any C++ signature, `git grep` the name over the whole tree
    (all of `.cpp/.h/.mm/.cc`), not just the file being edited. Same for
    NSIS: `makensis` only runs at package time, so a deleted `.nsh`
    function reads as fine until `mach package`.
26. **⚠️ Deleting a file? Grep the build files for its name.**
    `toolkit/components/telemetry/pings/UntrustedModulesPing.sys.mjs` was
    deleted while still listed in `EXTRA_JS_MODULES`, and `config.status`
    died on `File listed in FINAL_TARGET_FILES does not exist`. After every
    deletion, `git grep -F <filename> -- '*.build' '*.mozbuild' '*.mn'
    '*.ini' '*.toml' '*.list'`. The metrics/pings yamls are consumed through
    `metrics_index.py`, so they need no per-file entry — but anything in
    `EXTRA_JS_MODULES`, `UNIFIED_SOURCES`, `EXPORTS` or `INSTALLER_FILES`
    does.
27. **⚠️ Removing a recording can orphan its whole data path — check
    both directions.** Cutting `glean::widget::ime_name_on_windows` left
    `GetActiveTIPNameForTelemetry` with no callers; cutting the CRLF
    recording left the `numberOfCRLFs` lambda computing into the void. After
    every recording removal, grep the helper it fed on (`key` builders,
    label mappers, counter lambdas) and confirm a live reader remains.
    The reverse also bites: `MediaGleanMetrics.h` looked live because
    `MediaFormatReader.cpp` included it, but the include was the only use
    left after the recording went. And a removed parameter cascades upward:
    `aName` died in `MaybeReportAccumulatedTime`, which killed it in
    `RunnableDidRun`, which killed it at all three call sites — each level
    would have been `-Wunused-parameter` under `-Werror`.
28. **⚠️ `git grep` over the full tree hangs on this machine; scope it.**
    A bare `git grep -n <pattern>` (or a Python `rglob` walk) routinely
    exceeds 2–5 minutes and times out. Ripgrep through the `grep` tool with
    a tight `path` (`xpcom/`, `toolkit/`, …) plus `include`, or `git grep`
    with a pathspec, returns in seconds. Never gate a decision on a grep
    that timed out — an empty result from a killed search reads exactly like
    "no callers".
29. **⚠️ `node --check` every JS file the stack touches — and distrust the
    first error.** A telemetry patch left an orphaned `try` (its `finally`
    only submitted a ping) in `RemoteSettingsExperimentLoader.sys.mjs`,
    so the module never parsed and Nimbus died at startup. V8 reported it
    60 lines away (`Private field must be declared…`); acorn pointed at the
    real `Missing catch or finally`. Recipe: `node --check` over all
    touched `*.js/*.sys.mjs` (ignore `firefox.js`/`all.js`: `#` directives
    are false positives), then acorn for anything that fails. A module that
    does not parse breaks every importer, so this is a startup blank-page
    factory — add it to the hunt whenever the UI renders half.
30. **⚠️ `False` is not `None` at `set_define` — the three MOZILLA_OFFICIAL
    levels must agree.** `mozilla_official() → False` kept every CONFIG
    consumer dark (all use truthiness) but emitted `-DMOZILLA_OFFICIAL`
    *empty*, so the C preprocessor saw **official** while JS/Rust saw
    unofficial: official-only C++ compiled in, and `#ifndef`-guarded files
    (`browser-development-helpers.js`) were skipped by packaging while
    `browser-main.js` still loaded them — every window blank, no tabs, no
    keys. `None` leaves the macro undefined and restores exact
    upstream-unofficial semantics on all three levels (the env pin still
    holds). Whenever a configure value feeds both `set_config` and
    `set_define`, test the *preprocessor* meaning, not just the boolean.
31. **⚠️ The exe does not depend on the branding .ico files.** Editing or
    regenerating `browser/branding/aether/*.ico` changes nothing in the
    binary: the link reuses `obj/browser/app/aether.exe.res` (compiled once
    from the .rc + .icos, with no tracked dependency). Deleting the dist
    exes alone re-ran LINK against the stale .res and shipped old icons
    twice. After any icon change, delete `obj/browser/app/aether.exe.res`
    (+ the dist exes) and rebuild, then verify by extracting icon group 0
    from the fresh exe with pefile — never trust timestamps or payload-size
    eyeballing (two different arts can share entry sizes). The affected set
    is `aether.exe.res`, `pbproxy/private_browsing.exe.res` (uses
    `PBMODE_ICO`) and `desktop-launcher/desktop-launcher.exe.res` (uses
    `FIREFOX_ICO`); a half-overlapped `mach build` that you killed leaves
    half-linked exes that `make` then considers up to date, so nuke both the
    .res *and* the dist exes every time.
33. **⚠️ The icon you see on `AetherSetup-<v>.exe` is the SFX module's, not
    the NSIS stub's.** `make-stub-offline.py` concatenates
    `branding/sfx-7zSD.Win32.sfx` + `sfx-config.txt` + `payload.7z` into one
    file, so Windows reads the icon off the **outer** SFX's own
    `RT_GROUP_ICON`/`RT_ICON`. Changing `Icon "…"` in `stub.nsi` (which is
    what `MUI_ICON` would have done) is invisible to the user: that only
    touches the `setup-stub.exe` extracted at runtime. Worse, the SFX is a
    prebuilt Mozilla binary and it still carried **Oxygen Browser's** icon
    (blue "O" in a box) — nobody noticed because no file in the repo
    referenced it. `scripts/patch-sfx-stub.py` rewrites those resources (and
    `VS_VERSIONINFO`, where "Firefox"/"Mozilla" become "Aether" via an
    equal-length UTF-16 substitution) through `UpdateResourceW`; it is
    idempotent because it always starts from
    `other-licenses/7zstub/firefox/7zSD.Win32.sfx`. It used to be dead code
    with hardcoded `C:\Users\Vic\…` paths from the old machine; paths are
    now derived from `__file__` with a `--src` for the worktree. It also
    used to resize from `Image.open(LOGO)`, which for an .ico opens the
    **smallest** frame — the 16px icon came out as mush; it now walks
    ICONDIR and downsamples from the 256px master. Verify with
    `scan-icons.py`-style pefile extraction, never by eye in Explorer alone.

35. **⚠️ `git apply --reverse --check` does NOT prove a section owns the
    file — only the hunks.** The Cancel button shipped solid slate
    (`#2A3344`) while patches 40 and 42 both said
    `background-color: transparent`: the colour lines sit *outside* every
    hunk, so all 27 sections of 40/41/42 reverse-checked green while the
    tree carried an edit no patch owned. A clean clone would have built a
    transparent Cancel — the exact bug already reported and "fixed" once.
    `git apply --reverse --check --include=<path>` proves the *hunks'*
    contexts match, nothing more; `git status` cannot see it either when the
    file is untracked (every file patches 40–42 create is `??`). The only
    test that catches it is whole-file: reconstruct the states
    (`final` → reverse 42 → reverse 41) and compare them against each patch's
    `+` image, which for a `new file` section is every `+` line concatenated.
    Do that before touching a file the stack creates.

37. **⚠️ Google Fonts dropped truetype; css2 serves woff2 only, and the
    axis is easy to lose silently.** The installer ships `@font-face` WOFF
    because the host is IE in Edge mode reading `$PLUGINSDIR` at install
    time. Rebuild them with `scripts/generate-fonts.py` (needs
    `pip install fonttools brotli` on the mozilla-build python); do not hand
    -edit them. Three traps, all hit:
    * css2 returns woff2, so fontTools cannot read the download without
      `brotli`;
    * a modern UA makes css2 emit one `@font-face` per unicode subset and the
      **first block is vietnamese, not latin** — pick the block labelled
      `latin`, or you ship the wrong subset;
    * requesting a **single** weight (`family=Quicksand:wght@700`) returns a
      *static instance with no `fvar` table: every weight then comes out
      identical, silently. Request a **range** (`wght@300..700`) to keep the
      axis, and the range must be inside the real axis or Google answers
      **400** (Quicksand is 300..700, so `100..900` fails).
    The script asserts `usWeightClass` on every output for this reason.
  * **A WOFF change needs three places, not one:** the `@font-face` block in
    `stub_common.css`, the `File /oname=$PLUGINSDIR\…` lines in `stub.nsh`
    (three sites) **and** `stub_helpers.nsh` (one), **and** the file list in
    `browser/installer/windows/Makefile.in`. Miss the makefile and the build
    dies with `No rule to make target '…/quicksand-medium.woff'` — that error
    naming a *font* is the tell that the makefile still lists the old set.
    A `mach build` that was already running when you edit `Makefile.in` keeps
    using the stale generated copy and fails the same way; just re-run it.
  * **Quicksand and Comfortaa both stop at 700.** There is no 800/900 in
    either family; if a heavier rounded title is ever wanted it has to come
    from a different family (Figtree reaches 900, Nunito 1000).

38. **⚠️ Regenerating a middle patch needs a real clone, not a hand-built
    pre-state.** Patches 40-42 had never been through gate 2, which hid two
    bugs and then cost an afternoon:
    * **41 and 40 both added the same two lines** to `getUIString` in
      `stub.nsh` (`${Case} "welcome_splash"` + `Push
      "$(STUB_WELCOME_SPLASH)"`). Duplicate ownership, so 41 could not apply
      on top of 40 at all. The tell is the error naming a line that already
      holds what the patch adds.
    * **Hunk headers cannot be hand-edited.** Removing two `+` lines from
      `-426,6 +426,8` leaves `-426,6 +426,6`; getting the count wrong yields
      `corrupt patch at N:line`, which is *not* `does not apply` and sends you
      looking in the wrong place. Three attempts failed on this before
      rebuilding the whole patch from `git diff`.
    The method that works, and the only one to use again: keep a clean clone
    at the base commit, apply the series patch by patch with `git apply`
    (`applystep.py` pattern: report every step, stop at the first failure),
    and rebuild the suspect patch with `git diff --no-index` between the
    clone's current file and the worktree's. Then `git apply` the rebuilt
    patch to advance the clone. Text via `--no-index`; binaries staged in a
    scratch repo so git emits a real `GIT binary patch` payload (plain
    `--no-index` will not, and `git apply` rejects binaries without it).
    Rewrite the `a/`/`+++` headers by hand: `--no-index` writes the absolute
    paths, quoted and backslash-escaped on Windows, which produces
    `inconsistent new filename`.
    **Never mutate the gate-2 clone to experiment on it.** A
    `git checkout -- <dir>` there leaves the tree half-reverted and every
    later conclusion is worthless; rebuild the clone from the base commit
    instead (`git clone --shared --no-checkout` + `checkout <base>` +
    applystep.py). Note `sync.py` is **not idempotent** on a dirty tree: it
    re-applies from patch 01 and conflicts, so it cannot be used to
    re-verify a partially applied clone.

    source file to CRLF, and the patch that carries it will not notice.**
    Removing the dead `ExtensionTelemetry` call sites used
    `Path.write_text(encoding="utf-8")` for every edit; on Windows that
    translates each `\n` to `\r\n`, so seven files under
    `toolkit/components/extensions` and `browser/components/extensions` came out
    CRLF while the tree convention is LF (`.gitattributes` says `* -text`, and an
    untouched sibling confirms it). Use `write_bytes()` for anything that ends up
    in a patch - this is trap 16 again, one level up. It stays invisible
    because all three of the usual checks pass:
    * `git apply --check` passes: the patch applies perfectly;
    * the tree still builds: CRLF files are still valid JS;
    * `git status` shows nothing unusual.
    The only tell is the **shape of the generated diff**: two deleted lines came
    out as `@@ -1,4744 +1,4741 @@`, a whole-file rewrite of a 4744-line file.
    Two rules for any regenerated patch:
    * before generating, assert both sides agree on line terminators (one
      `count(b"\r\n")` each); that is the precondition for a minimal diff;
    * after generating, assert the section is not a whole-file rewrite -
      `minus > 0.9 * old_lines` means something rewrote the file instead of
      editing it, **unless** the file genuinely shrank. The telemetry module went
      175 -> 31 lines, which is a legitimate 95% diff, so the guard has to
      allow for the file's actual size change rather than use a fixed ratio.

39. **⚠️ PNGs store RGB=black under alpha=0, and downscaling bleeds it.**
    `aether-mark.png` has `(4, 3, 3, 0)` in its corners, so a plain LANCZOS
    resize from 3301px to 24px mixes black into every edge pixel and the mark
    comes out muddy dark — which then reads as "the link is stale" and sends
    you deleting .res files forever. `deflate_background()` in
    `scripts/generate-icons.py` fixes it by compositing neighbor hues into
    the fully-transparent zones before the resize. Its blur radius is
    load-bearing: 16 still produces dark 24px entries, 28 is correct on light
    *and* dark backgrounds. Prove icon changes by rendering the entry to PNG
    and looking at it; mean brightness and payload sizes both lie.

40. **⚠️ `write_text()` on Windows silently rewrites a source
    file to CRLF, and the patch that carries it will not notice.** Removing the
    dead `ExtensionTelemetry` call sites used `Path.write_text(encoding="utf-8")`
    for every edit; on Windows that translates each newline to CRLF, so seven
    files under `toolkit/components/extensions` and
    `browser/components/extensions` came out CRLF while the tree convention is
    LF (`.gitattributes` says `* -text`, and an untouched sibling confirms it).
    Use `write_bytes()` for anything that ends up in a patch - this is trap 16
    again, one level up. It stays invisible because all three of the usual
    checks pass:
    * `git apply --check` passes: the patch applies perfectly;
    * the tree still builds: CRLF files are still valid JS;
    * `git status` shows nothing unusual.
    The only tell is the **shape of the generated diff**: two deleted lines came
    out as a whole-file hunk over a 4744-line file. Two rules for any regenerated
    patch:
    * before generating, assert both sides agree on line terminators; that is
      the precondition for a minimal diff;
    * after generating, assert the section is not a whole-file rewrite. A fixed
      ratio is not enough, because a file that genuinely shrank (the telemetry
      module went 175 -> 31 lines) legitimately diffs almost entirely. Compare
      against the file's actual size change instead.

41. **The build does not check that JS modules exist; removing a dir
    from DIRS orphans whoever still imports from it, and only runtime tells
    you.** The Sync wipe dropped "syncedtabs" from browser/components DIRS,
    so its EventEmitter module is never staged and never reaches omni.ja -
    while webrtcUI.sys.mjs imported it at its top level. The first page to
    touch WebRTC then died loading the module (Failed to load ...
    EventEmitter.sys.mjs), which can break the camera/microphone flow
    rather than just log noise. Nothing in the build noticed: mach build,
    mach package and `git apply --check` all pass, and gate 2 compares
    trees that share the same hole. After removing any module or dir from
    the build, grep the tree for imports of its path (`moz-src:///...` and
    `resource://` forms) and confirm every remaining importer still
    resolves to a packaged file (7z l on omni.ja). The fix cut the
    consumer instead of re-listing the dir: nothing in shipped code
    emits those peer-request events and nothing subscribes, so the import,
    the property and the live on/off went away (on/off stay as documented
    no-ops for add-on compat). Related: never `git checkout -- <file>` in
    the worktree to revert one edit - it restores upstream base and wipes
    every patch's changes to that file; copy the file from the clone,
    which holds the true stack state.
42. **DevTools CJS modules have no bare `performance` global, and the
    failure mode is total.** Replacing `Services.telemetry.msSinceProcessStart()`
    with `performance.now()` in `devtools/client/shared/telemetry.js`
    threw `ReferenceError` inside the `Telemetry` constructor, and since
    every tool does `new Telemetry()`, DevTools would not open at all.
    In that scope the clock is only ever reached off a window
    (`this.win.performance.now()`); with no window at hand use `Date.now()`.
    Neither `node --check` (syntax only) nor the build notices - the module
    parses and packages fine. If DevTools break after touching that file,
    check globals first.
43. **An orphaned `using namespace` survives on unified-build leakage and
    breaks when the TU stands alone.** `PeerConnectionImpl.cpp` carried
    `using namespace Telemetry;` with no include and no remaining use; the
    full build passed (some other TU in the chunk leaked the header) and an
    incremental build failed with `expected namespace name`. The error
    points at a line no patch touched, which sends you looking in the
    wrong place. After removing any include or the last use of a
    namespace/API in a file, grep the file for leftover `using`s and
    unqualified uses - the build only catches it when chunking changes.
44. **Leftover headless smoke processes lock `omni.ja` and fail the
    package with `OSError: [Errno 22]`.** A headless `--screenshot` run
    that hangs (or is killed by timeout) leaves `aether.exe` + content
    processes alive holding the packaged `omni.ja`, and the next
    `mach package` dies rewriting it. Before rebuilding after smoke
    tests, kill test processes by command line (`obj-aether` in it) -
    never blindly: the user's real browser must not be touched. Standing
    permission (2026-10-10, user does not day-drive any `aether.exe` build;
    daily driver is stock Firefox until Aether ships): any `aether.exe` may
    be killed when it blocks packaging. Never touch `firefox.exe`.
45. **Never run raw `mach build/package`: always export `MOZCONFIG`
    (repo `mozconfig.windows`, official Aether branding) first, or use
    `scripts/windows/run-build.cmd` + `run-package.cmd` with
    `FIREFOX_SRC` pointing at the worktree.** Without it mach silently
    reconfigures the objdir to `unofficial` branding (firefox-named
    packages, `dist/firefox` instead of `dist/aether`), and every later
    check runs against the wrong binaries.
46. **Removing the last `ExperimentAPI.init()` caller hangs every
    `NimbusFeatures[x].ready()` await forever, with zero log output.**
    Upstream `Normandy.init()` (via `FirstStartup`) was the only
    production caller; deleting Normandy left the ExperimentStore
    SharedDataMap permanently pending, and `AboutNewTab.onBrowserReady`
    waited on it before creating ActivityStream - blank newtab, null
    stream, no error anywhere. After deleting experiment machinery,
    grep the startup paths for remaining `.ready()` / `NimbusFeatures`
    awaits instead of trusting "no errors".
47. **A blank newtab under Marionette proves nothing: automation
    forces minimal newtab feeds.** `remote/shared/RecommendedPreferences`
    sets `browser.newtabpage.activity-stream.testing.shouldInitializeFeeds`
    to false for every WebDriver session, so `newtabinit` never registers,
    the state request is never answered and `#root` stays empty without a
    single error. Verify newtab headed with plain runs and stdout-captured
    `dump()` markers (parent `AboutNewTabParent` handshake, content store
    state), never through Marionette/CDP navigation.
48. **`sync.py --apply` cannot resume on an already-stacked tree.**
    It walks the series from 01: forward-apply fails (later patches
    already changed the context) and reverse-check fails too (same
    reason), so it stops at 01 with a bogus CONFLICT. It is pristine-trees
    only. To continue a stacked tree, apply the remaining patches
    one by one with `git apply` in series order. (Found while
    re-running gate 1 from scratch; the keeper clone is `C:\cr\u2`.)
49. **Amending a patch? Its pre-state is the true predecessor, never the
    already-amended state.** Regenerating a section as diff(amended-tree)
    bakes later content into an earlier patch and the fresh gate-1 fails
    exactly there (hit twice: 153's engine section after the 151 regen,
    156's binding section after its own amendment). Recover the true
    pre-state by reverse-applying the patch's own section onto the stacked
    clone, diff against the worktree, and re-prove with a fresh gate-1.
50. **`nsIStreamListener.onStopRequest` takes `(request, statusCode)`: there
    is no context argument.** Passing the status where `nsISupports`
    context belongs throws `NS_ERROR_XPC_BAD_CONVERT_JS` at the call site;
    capture the real context in `onStartRequest` and reuse it. (Found
    tracing surrogate delivery: every downstream call "succeeded" loudly
    except the mistyped one, which died silent inside try/catch.)
51. **Disposable `omni.ja` pokes must never be "restored" from a backup
    taken before the last build.** A stale backup restored over a fresh
    package silently reverts the binary under test, and every later
    conclusion (including green gates) validates the wrong code. Either
    repackage after poking or delete the backup so a restore fails loudly.
    (A whole redirect-gate afternoon went to a stale backup.)
---

## 9. Current state and open decisions

- **All five gates green (this session).** 1: the series applies to a clean
  checkout with 0 conflicts. 2: **whole-tree comparison green, 2,323 files
  touched in both trees, 0 exclusive, 0 differing contents** (SHA-256 per
  file) — the first time gate 2 has run with the installer patches. 3:
  privacy defaults `TODO OK`. 4: build + package exit 0. 5:
  `aether.exe --version` prints `Aether Aether 156.0.1`.
  Gate 2 needs `sync.py`'s **branding step run on the clone** before it can be
  compared: the series carries only text and SVGs, so the PNG/ICO/ICNS assets
  and the installer SFX are copied in afterwards. Without that
  step the comparison reports ~70 phantom differences. Also note the tree's
  `browser/branding/aether/setup-hero.png` had gone stale against `branding/`
  (branding wins, per trap 2) — that is what the last differing file was.
- **The series is now 119 patches (core/01–121, with 11 and 19 unassigned).** The tail was folded by hand
  (there was no history to rebase, since nothing had ever been committed):
  - `34-final-cleanup-sweep.patch` = the old 34 (final Glean sweep) + 35
    (installer telemetry) + 36 (MSI/MSIX out) + 37 (Nimbus orphaned try)
  - `35-installer-ux.patch` = the old 39 (ARP naming) + 40 (welcome gate) +
    41 (splash fade) + 42 (modern UI) + 43 (setup icon)
  The originals are in `%TEMP%\opencode\aether\patches-34-43-originals\`.
  **A fold always needs the full revalidation** — gate 1 and gate 2 were both
  re-run green after this one, which is the only reason to trust it.
- **Two stack bugs found and fixed once gate 2 ran on the installer patches**
  (which had never been done — the last green gate 2 was at 01-39):
  * patch 40 and patch 41 both added the same `welcome_splash` case to
    `getUIString` in `stub.nsh`, so 41 could not apply on top of 40 at all;
  * the hunk headers were then hand-edited to drop the duplicate, which turned
    "does not apply" into `corrupt patch` three times over. Both patches are
    now regenerated with real `git diff` output (see trap 38).
- **Installer polish (this session).** The stub's `Icon` line now points at
  `setup.ico` (the box) so the Setup UI does not wear the browser flame, and
  `scripts/patch-sfx-stub.py` — long dead with hardcoded `C:\Users\Vic\…`
  paths — was repaired and is what actually rewrites the icon in the
  **prebuilt SFX module**, which is where the icon the user sees comes from.
  The Cancel button is red (`#B32F45`, 6.2:1 against its white label), the
  typography is Quicksand Bold for titles and Comfortaa for body and buttons
  (both OFL), and the three WOFFs are rebuilt by `scripts/generate-fonts.py`
  from the variable sources in `branding/source/fonts/`.
- **`CHANGELOG-0.1.md`** enumerates all 119 patches for the release commit,
  generated from the patch headers themselves so it cannot drift. Not pushed;
  the release commit is still not made (the user wants to write one general
  commit enumerating 0.1's changes).
- **`scripts/patch-sfx-stub.py` is no longer dead weight** (an earlier
  revision of this file said it was): it is the only thing that can restyle
  the SFX icon, and it must be re-run whenever the SFX or the icon changes.

- **Done:** groups 29–32 (Optional Features, dead pings, gecko-trace +
  OpenTelemetry out, installer telemetry out). Comments and docs in English, no
  internal markers. Local changelog removed (the news goes on the website).
  **All five gates green**: 30/30 patches apply with 0 conflicts, clean clone
  tree identical (17,469 files, 0 differences), privacy defaults `TODO OK`,
  build and package exit 0, `aether.exe --version` prints
  `Aether Aether 156.0.1`.
- **Done (block A):** the C++ Glean writers pass, as patch 33
  (`33-last-glean-writers.patch`, extended to 20 sections): XPConnect
  memory reporters, power metrics, the cycle-collector/quota leftovers, the
  macOS printing hook. `RecordPowerMetrics()` stays (profiler markers only),
  `TestTriggerMetrics` stays (test-only IPC plumbing).
- **Done (block B):** the final Glean sweep, as two new patches —
  `34-final-glean-sweep.patch` (57 sections: the five missed live-writer
  sites `system_cpu.*`/`longtask`/`ime_name_*`, the four Rust SDK
  self-measurements, all twelve production `metrics.yaml` plus the
  third-party-modules `pings.yaml`, the 24h `UntrustedModulesPing` and its
  `submitAndGetUntrustedModulePayload` API, the orphaned `printing`/`widget`
  legacy mirrors, the broken Glean-asserting gtests) and
  `35-installer-telemetry.patch` (10 sections: `telemetry.nsh` deleted, the
  phase-timing Vars, `TELEMETRY_*` defines, `un.SendUninstallPing` renamed
  to what it does, the nsis `Makefile.in` test-deps). Gates 1/3/5 green on
  the result (build OK, installer + stub + zip packaged, makensis clean on
  all four scripts); `reverse-check` 0 on both patches.
- **Gate 2 green at last (this session).** It caught two real stack bugs no
  other gate sees: (a) patch 32 carried hunks patch 01 already owned (SFX
  branding, `setup.ico`, most of `makensis.mk`) — 32 is regenerated down to
  its unique contribution (`launch.*`, dropping `HttpPostFile.dll`);
  (b) patch 33's `CrashManager` section was generated against a corrupt
  pre-state and dropped the `} catch (ex) {` line, leaving broken JS
  (`console.error(ex)` with no `catch`) — tree repaired, section
  regenerated, 33 now applies forward AND reverses. The same rule folded the
  MOZILLA_OFFICIAL None fix into patch 10 (which owns the pin) instead of a
  new patch 38: fix the patch that breaks, don't stack on top — a middle
  patch can only be reverse-checked per-file (`--include`), never whole,
  against a tree with later patches on top. Confirmed fixed in the wild:
  reinstalling the None build renders the full UI (tabs, urlbar, content);
  the False build had left every window blank. Final, re-run with the
  finished series (01–39, 38 folded into 10): **36 applied, 0 conflicts;
  17,499 files touched in both trees, 0 exclusive, 0 differing contents**
  (1,431 byte-compared). Three stray unreferenced branding pngs moved out
  of the tree to `D:\oxygen-backups\blockB-stray\` to get there.
  The old "30/30 without conflicts" claim is superseded by this run.
- **Done (block B continued):** `36-msi-msix-out.patch` (9 sections) removes
  the MSI (`installer.wxs`) and MSIX sources plus their docs, which this
  build never generates and which contradict the per-user no-UAC model.
  The files live in the PRIVATE backup `D:\oxygen-backups\msi-msix\` (not
  public, not in any patch) with a restore README; `mach repackage`
  tooling untouched. Gates 1/3/5 green, build OK (the pipeline regenerates
  `AetherSetup-156.0.1.exe`, 91,7 MB, by itself).
- **Done:** `37-nimbus-orphaned-try.patch` (one line: orphaned `try` → bare
  block; an earlier patch had removed its `finally`, leaving a module that
  never parsed) and `39-arp-display.patch` (ARP reads "Aether Browser (x64)
/  0.1 / Aether Group": no locale in the name, distribution version from
  distribution.ini with AppVersion fallback, publisher fixed in both
  installers; 156.0.1 stays internal). Icons: `generate-icons.py` set to
  photographic at all sizes (SMALL_SIZES=0, silhouette kept in code) and
  regenerated from the purple master — the shipped ICOs predate the
  silhouette path and carry a washed white variant; taskbar renders the
  design intact (verified side-by-side at 24px).
- **Branding split (deliberate, do not "fix"):** everything uses the
  photographic purple flame *except* `pbmode.ico`, which keeps the original
  white variant so private windows stay visually distinct. It was once
  overwritten with the rest and had to be restored byte-identical
  (hash-matched) from the installed exe's resources — treat `pbmode.ico`
  as frozen. Same for `setup.ico` (box art, intentionally different).
- **Kept on purpose:** the `nsSystemInfo` locals/tables (still fill the info
  struct), `mActiveTIPKeyboardDescription` + `GetTIPDescription` (IME
  checks/logging/getter), `sLatestIMEOpenedModeInputSourceID` (macOS paste
  path), `pings_per_interval` (rate limit), `getUntrustedModuleLoadEvents`
  + serializer (about:thirdparty), `SendPing` (stub exit work),
  `$PostSigningData` (attribution, no send), `GetInstallationTelemetryFromMsi`
  (MSI source read for the launcher handler), the TEST metrics yamls and
  `TelemetryTestFixture` bases. `tools/@types/generated/lib.gecko.xpcom.d.ts`
  still mentions the removed IDL method (generated IDE tooling).
- **Group 32 / installer:** the shipped setup is the **Firefox NSIS stub**,
  offline. `mach package` produces the full installer and `setup-stub.exe`
  (`MOZ_STUB_INSTALLER=1`), and `make-stub-offline.py` packs both into
  `AetherSetup-<version>.exe` (~93 MB, SFX + payload) so it installs with no
  network. Patch 32 is what makes that possible: it reads the payload instead of
  downloading, and it is also where the **installer telemetry was removed**
  (`SendTelemetryPing`, the ping after uninstall, the post-uninstall survey) plus
  the auto-elevation (`${ElevateUAC}` in `CommonOnInit`), so the stub never asks
  for admin. Installs to `%LOCALAPPDATA%\Aether Browser` without UAC; only a
  launch "as administrator" picks `Program Files`.
  The stub finishes on its own page asking whether to launch the browser
  (`content/launch.html` + `launch.js`, silent installs keep upstream behavior).
  Patch 40 adds the welcome gate up front (`content/welcome.html` + `welcome.js`
  + `welcome_page.css`, Start/Cancel; silent skips it, Cancel exits with the
  before-download code).
  `build.py` fails if `uninstall/helper.exe` goes missing. The uninstaller and
  the maintenance-service installer stay: they ship inside the browser and the
  updater needs them.
- **Patch-count discipline:** the series stays granular while working (one
  validated unit per patch: 34–40 in this session alone). Squash with
  `rebase -i` when ready for GitHub — never mid-work, every fold needs full
  revalidation (build + gates + gate 2).
- **Done (dead call-site blocks 36–107):** ExtensionTelemetry, Nimbus, autofill, startup-module,
  BrowserUsageTelemetry shells, WebRTC emitter, telemetry events, translations sink, usage calls,
  AboutWelcome, newtab/DoH, search, legacy callsites, ext-telemetry API, payload flows, ASRouter flow,
  client-env/teleportals, targeting attrs, clientID replacement, environment readers, reporting policy,
  experiment-env mirror, restored backends, util readers, backend JS, orphan enums/includes, GIFfT/MaRS/
  Pocket/manual-updates/viaduct/crash/newtab/search/suggest/URLbar-engagement/FOG/sponsor-protection/
  data-submission/AI-window/logins-migration-password/usage-addon-tabnotes/sponsored-attribution/
  third-party-leftovers/sponsored-attribution. Gate 2 green at 101
  (REF vs WORK: 0 differing files), gates 3/5 green (`TODO OK`, `Aether Aether 156.0.1`).
  The `isSponsored` display flag and its readers stay (badge + filtering, not telemetry).
- **Done (102: Glean DOM gone):** the three Glean WebIDL files and their `window.Glean`/
  `window.GleanPings` attributes, the Bindings.conf block (including `nsIGleanPing`), the
  `nsGlobalWindowInner` accessors plus their cycle-collection traffic, the DOM-only C++ classes,
  the whole C++ metric-type layer behind them (private/*, GleanMetric, MetricTypes, generated JS
  lookups, GleanPing, FOG/TestFog/legacy event-histogram-scalar gtests, dead GPU/profile includes)
  and the empty ReportBrokenSite recorder - verified zero in `xul.dll`
  (`GleanPingsImpl`/`DefineGleanPings`/`GleanCategory`/`GleanWebidlEnabled` all absent).
  What stays, with reason: the standalone no-op declarations (the JS engine links them), JOG, FOG IPC,
  the codegen rules, the Rust SDK with its neutered uploader. Seven build iterations; the compiler
  audited each layer (undeclared-identifier, missing-header, undefined-symbol, in that order).
- **Done (103: telemetry docs gone):** both doc trees (`telemetry/docs`, `glean/docs`, 58 files) plus
  sphinx registrations and lint exclusions. Docs never shipped in the product.
- **Done (104: extension Glean global gone): the `Glean`/`GleanPings` globals injected into every extension sandbox threw `ReferenceError` at each creation (found live via crash-tracker on YouTube; the JS API behind them is gone). YouTube crash report: build-49-only, does not reproduce on current builds.
- **Done (106: sync promos, widgets and send-to-device UI):** the welcome sign-in buttons and device-migration screen, the share-panel device flows, the tour account actions, the sync/send-tab toolbar widgets, the places promos, the tab-context send updater and the sync-promo element. The 105 regen had already absorbed the welcome/share/tour work (headers fixed on both). Proven: about:welcome loads with zero chrome errors.
- **Done (107: Normandy gone):** build flag off, component deleted (67 files), startup/quit hooks, the extension study API, Nimbus rewired to local UUIDs, troubleshoot/test cleanups. The compiler audited it in layers (webidl codegen, missing headers, undefined symbols, startup module throw). Smoke-caught regression included: a deleted permission constant broke `Extension.sys.mjs` at startup and cascaded into preferences init - fixed, rebuilt, zero chrome errors.
- **Done (108: Normandy fallout on newtab fixed):** with Normandy gone nothing calls `ExperimentAPI.init()`, so the Nimbus store never resolves `ready()` and `AboutNewTab.onBrowserReady` hung forever before creating ActivityStream - blank newtab, null stream, no error logged. Newtab startup no longer waits on Nimbus (local pref defaults only); the dead `Glean` sandbox global is out of the DevTools loader (that ReferenceError had also killed the browser console and derived the `lazy.Telemetry` failure); the last live `NewTabGleanUtils` site is out of the newtab resource mapping. Diagnosed by `dump()` stage markers patched into a disposable `browser/omni.ja` (handshake traced hop by hop, content store proved `App.initialized=true`), then fixed in-tree. Traps: silent Nimbus hangs are #46, Marionette's forced minimal newtab feeds are #47. Gates: series OK (42 applied, 64 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, `Aether Aether 156.0.1`, headless smoke 0 chrome errors, headed newtab renders (user-confirmed), MAR rebuilt with matching BuildID, self-test OK.
- **Done (109: RFP off by default, code kept):** `privacy.resistFingerprinting` default `true`→`false` in `firefox.js` (one pref + comment, code untouched) so our graded system can be measured without RFP masking it. Accepted interim cost: weaker fingerprinting until our layers land; supersedes the old do-not-touch-RFP rule per user decision. Gates: series OK (42 applied, 65 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0, version string, packaged `firefox.js` verified carrying `false`, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (128: normalize touch points with a Settings toggle):** touch laptops report rare maxTouchPoints values (7+ bits on CoverYourTracks). Window Navigator reports 0 behind master + kill prefs with the usual per-site exemption restoring the real count; own toggle next to the fingerprinter switch at the top of Settings > Privacy & Security (config entry, checkbox, en-US FTL). Gates: normalized 0 by default PASS (headed live-toggle off follows the widget, which reports 0 in test windows); series OK (51 applied, 80 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke on about:preferences 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (129: restrict page-visible fonts with a Settings toggle):** font presence lists are ~5 stable bits. Documents resolve at Gecko base-system visibility behind master + kill prefs, and Aether additionally hides the Windows families that carry edition/Office signal but no glyph coverage of their own (decorative and bundled-Office families only; CJK, Indic, Thai, symbol-coverage and locale fonts stay visible so text never falls back to tofu). Chrome, devtools, RFP-exempt documents and Aether-exempted sites resolve at a higher level and are unaffected; OffscreenCanvas contexts inherit through the standard provider chain. Own toggle next to the other switches at the top of Settings > Privacy & Security; webfonts via @font-face keep working. Debugging: IsVisibleToCSS is the single funnel for every CSS font lookup; its first version inverted the default (it exposed user-installed fonts at Base level) and left the pref check orphaned (unused-function warning) - both fixed before shipping. Residual: Segoe UI Black/Semibold/Semilight and MS Serif resolve through style-linking/substitutes to the visible Segoe UI family (shared metrics, marginal signal); narrowing the parent would break all UI text. Gates: fonts-on (54 -> 29 detected, proper subset, Arial kept), fonts-off (54, equals baseline) and exempt (54, equals baseline) PASS; series OK (127 applied, 0 already there, 0 in conflict), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke (about:preferences#privacy renders 1366x768, stderr clean apart from known headless artifacts; packaged firefox.js verified carrying the new default), MAR rebuilt with matching BuildID. Log-driven hardening: chrome documents skip the restriction (UI icon fonts were blocked); content gates re-green.
- **Done (130: single-entry language list and Accept-Language with a Settings toggle):** secondary languages are stable cross-site linkers while adding nothing to negotiation. navigator.languages truncates to the top entry behind master + kill prefs (navigator.language is languages[0], so it stays coherent); the HTTP Accept-Language header is cut to its first token at the channel layer, where redirects re-enter per hop and every hop is re-evaluated against its own target. Workers share one global list and cannot prove first-party off-thread, so they truncate without exemption; an explicit language override (containers) always wins. Third-party targets always truncate so an exemption never leaks the full list to embedded trackers; first-party targets keep the full list only where the top site is exempted. Own toggle at the top of Settings > Privacy & Security. DNT stays off (deprecated; sending it is itself a minority signal) and GPC is left at stock default for the same reason. Debugging: HttpBaseChannel needed the fully-qualified mozilla::dom::AetherCanvasNoise name (net namespace), a stray quote broke an include, and SetHeader is nodiscard - all fixed with 0 warnings. Gates: langs-on (single entry in navigator and both first/third-party echoes), langs-off (full list and full echoes) and exempt (full navigator, full first-party echo, truncated third-party echo) PASS; series OK (128 applied, 0 already there, 0 in conflict), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke (about:preferences#privacy renders, stderr clean; packaged firefox.js verified carrying the new default), MAR rebuilt with matching BuildID.
- **Done (131: stock 24-bit screen depth with a Settings toggle):** real hardware is 24-bit almost everywhere, so this is ~0 stable bits on typical setups; the setups that are not (16-bit RDP/VM sessions) are a telling minority worth covering. screen.colorDepth and screen.pixelDepth (ColorDepth delegates to PixelDepth) report 24 behind master + kill prefs with the usual per-site exemption; nothing derives layout from this value so there is no invariant to maintain. Own toggle at the top of Settings > Privacy & Security. Deliberately out of scope: screen geometry and devicePixelRatio. Monitor size is entangled with the real window size through hard invariants (innerWidth <= screen.width, fullscreen inner == screen > avail); any lie big enough to matter breaks them detectably unless innerWidth and media-query evaluation are forked too (Tor-letterboxing complexity, not a layer), and CoverYourTracks itself observes screen size varies between visits. Gates: depth-on/off/exempt PASS (24 everywhere on 24-bit hardware by construction; gates verify plumbing and no-breakage); series OK (129 applied, 0 already there, 0 in conflict), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke (about:preferences#privacy renders, stderr clean apart from known headless artifacts), MAR rebuilt with matching BuildID.
- **Done (132: UTC timezone opt-in with a Settings toggle):** the OS zone is ~6 stable bits. Behind master + an opt-in pref (off by default), page Date/Intl and dedicated workers report UTC: window globals take it at global creation through the same realm-override seam automation uses (explicit overrides still win, chrome globals keep the real zone), and document-created workers take it at creation on the parent thread where prefs are readable. Nested workers inherit it from their parent. The usual per-site exemption restores the real zone. Own toggle at the top of Settings > Privacy & Security. Residual: service workers have no document on their creation path and keep the OS zone. Gates: tz-on (UTC date/offset/zone in window and worker), tz-off and exempt (Madrid values back in both) PASS; series OK (130 applied, 0 already there, 0 in conflict), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke (about:preferences#privacy renders, stderr clean), MAR rebuilt with matching BuildID.
- **Done (133: render the Settings toggles in the settings redesign):** the six switches lived only in the legacy template UI, which is never stamped while browser.settings-redesign.enabled is on (our default): Privacy & Security showed nothing of ours. They are now a first-class aetherProtections setting group right after the ETP status card (one addSetting binding per pref, moz-checkbox controls, human descriptions on every label, search-indexed); the legacy groupbox stays as fallback. Root-caused from a user report plus a tall headless screenshot; Marionette cannot script privileged contexts and the CDP /json routes are httpd-only in this build, so verification is visual + chrome-log. Gates: tall-viewport screenshot shows all six toggles with correct defaults (five on, UTC off), stderr clean of settings errors; series OK (131 applied, 0 already there, 0 in conflict), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, MAR rebuilt with matching BuildID.
- **Done (134: fine-grained fingerprint switches with a master toggle):** six switches hid the real breadth (canvas/WebGL/audio/cores/text noise had kill prefs but no UI, no master at all). The group now lists every layer individually with the master first, plus the two stock opt-ins (WebGPU allow, UA token) bound directly with no engine change; legacy template fallback mirrors the list. Master verified to gate all noise layers in KeyForPref (blocking stays independent by design). Gates: tall-viewport screenshot shows all fourteen toggles with correct defaults, stderr clean apart from two pre-existing unrelated errors; series OK (132 applied, 0 already there, 0 in conflict), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, MAR rebuilt with matching BuildID.
- **Done (135: standalone settings skeleton):** first step of the independent settings menu. about:aethersettings serves a static skeleton ported from the user mockup (layout, all three theme variable sets, sixteen icons, dashboard, quick cards, featured banner, stub); remote webfont dropped (offline rule), no scripts, en-US copy. Debugging: the docshell redirector was the wrong table (about: hung); browser/components/about/AboutRedirector.cpp + components.conf is the right one. Gates: about: renders the full design headless, chrome URL renders too; series OK (133 applied, 0 already there, 0 in conflict), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, MAR rebuilt with matching BuildID. Revised per direction: header tools out (no FPS meter, no theme seg, no accent swatches here; Light/Dark/Purple set stays for the theme work, fluidity-at-refresh is a standing principle); CSS machinery kept. Appearance section added in the same patch (single living patch for the new menu per direction, no 137): big box with Browser color picker (three per-card-scoped theme cards, accent ring + new tick badge with per-card contrast), theme persists in aether.settings.theme, dashboard status follows, minimal section switching; page is chrome-privileged now. Debugging: URI_MUST_LOAD_IN_CHILD contradicts IS_SECURE_CHROME_UI (hung loads) — dropped; Enter does not activate buttons via WebDriver keys, Space does. Gates: light/dark init renders, keyboard E2E (nav switch, purple and dark select with ring+tick on all three, prefs.js persistence), stderr clean. Sidebar refinements in the same patch: wider bar, larger type and icons, selected category as an accent pill with on-accent text, theme-face dots removed (tick kept), snappier wheel (notch 32, cooldown 250ms), explicit fade-out/in on swap with a generation guard. Wheel E2E re-green. Appearance refinements in the same patch: eyebrow out, normal-size crumb, duplicate box header out, smaller titles, off-accent selection ring plus matching tick, Website appearance menu wired to the stock content-override pref (keyboard E2E with persistence). Refinement in the same patch: snappier wheel, explicit fade-out/in, theme-face dots out, headers in the Setup face (Segoe UI). Theme cards reworked in the same patch: neutral cards, swatch-only color, tick-only selection everywhere, invalid focus_outline key Card restyle in the same patch: transparent cards, color only in the fluid swatch, tick-only selection on theme and web cards Appearance rebuilt in the row pattern (mockup previews with radio dots, accent swatches plus custom picker on one pref, Seven accents now (red, orange, yellow, green, blue, indigo, Custom accent is an in-page picker (SV square, hue bar, hex) instead of the native Windows dialog: live preview, commit on release, hex commits when complete and snaps back when invalid, Escape restores the accent the picker opened with; 31/31 E2E incl. restart persistence. Website appearance options use the real 44x32 mockup icons (ws-light, ws-dark, ws-sys composed via clip paths) at 50x36 in cards with a tick badge and accent border on the selected one, icon colours neutral grey (they stand for websites, not Aether), row inline again, 21/21 E2E incl. pref write; Protection section renders the fourteen settings from one registry in three row-pattern groups, master greys gated rows, stock page already covers the same fourteen prefs, 12/12 E2E; Appearance carries an Interface design row for the same pref, 9/9 E2E, plus a restart banner with a Restart now button when the design differs from page-load time; violet) plus custom picker, keyboard E2E with persistence; website scheme as seg; Aether Light/Dark built-in themes with an Our favorites group; keyboard E2E with persistence). Appearance sections stack vertically now (option cards back to horizontal rows inside; verified wide and narrow with no overlap). Vertical option rows in the same patch (swatch left, name, tick right; keyboard E2E re-green with persistence). Fourth theme Black (true-black chrome and page theme, keyboard E2E with persistence) plus vibrant purple swatch fix. Honesty note under Website appearance (verified: the stock override flips matchMedia plus rendering; sites with a saved theme of their own ignore it). Card cleanup in the same patch: transparent cards, borderless swatches, web cards down to icon plus tick (verified wide). (verified at 1366 and 800 wide with no overlap). Light card fix in the same patch: explicit light scope plus white swatch, every card self-sufficient on any page theme. out of the purple manifest. Gates: user-log review, chrome font-block messages gone, fonts gates re-green, appearance screenshot with tick-only cards. Headers use the installer face (Quicksand Bold subset as data URI; the generator cannot emit binary additions, hence embedded text). Browser chrome follows the picker: new built-in Aether Purple theme plus compact light/dark, picker enables immediately, startup sync re-enables explicit choices only. Gates: headed shot shows the full purple browser, activeThemeID purple in profile, keyboard E2E on all three cards with persistence. Sidebar pass per direction: wider bar, larger type and icons, selected pill in accent fill with on-accent text, wheel over the sidebar steps categories rate-limited (accumulation plus cooldown, native scroll first at scroll range ends), compositor-only section swap. Gates: wheel E2E (one scroll steps once, three rapid scrolls step once), stderr clean. Flash fix per direction: the BrowserGlue startup sync is gone (it switched late: black first, purple after). enable() persists natively, so restarts apply the theme on the stock path with no code; the page reads extensions.activeThemeID back with our pref as fallback. E2E: click persists purple, restart keeps it.

- **Done (137: interface design switch):** one pref (`aether.ui.design`, default `aether`) with a helper module; hamburger Settings and both shields entry points gate on it with the stock fallbacks restored verbatim (no hamburger switch button: too invasive, Appearance on both sides is the only switch surface). Fingerprinting controls stay ungated in both settings pages. Gates: live chrome E2E (helper default, pref flip both ways, design button removed since, Settings routes to about:aethersettings vs about:preferences 4/4), packaged omni 7/7, stock settings regression clean. The switch is also inside both settings pages: an Interface design row in our Appearance plus Aether/Firefox radios in stock Appearance under Browser theme (with a legacy radiogroup fallback in Privacy, 4/4 XUL ids); a separate redesign group stamped zero items with no error despite a resolving setting, so the radios sit in groups that paint and fingerprinting stays fingerprinting. Cross-page coherence 3/3 (stock click flips the pref, our menu reflects it with no restart). Stock trust popup (the live entry point) carries our 12 toggles with master gating and expand, headed-screenshot verified; the protections-popup copy was reverted to keep one panel. Design switches raise a restart message bar plus Restart now button in stock Appearance (button has its own setting: nested items never stamp); the Restart buttons themselves are intentionally never clicked in tests. Dead ETP controls are hidden from both popups (markup hidden plus a display:none backstop citing the closed ETP-off decision): the trust ETP toggle section and, in the dormant protections popup, its master switch and fingerprinters row. Engine untouched, purely presentational; our twelve toggles are unaffected.
- **Done (140: motion-sensor shield):** Standard layer (`aether.fingerprinting.sensors`, default on): shielded windows are never registered as sensor listeners, so no motion, orientation, proximity or light events fire at all. Owns its registry entry and firefox default. Toggle in both settings with a breakage warning, row in our panel and the stock trust popup. Gates: synthetic test events arrive off (3 motion + orientation) and zero on; 17 toggles with pref write; stock checkbox visually confirmed. Full hide/show contrast needs hardware; empty-list behavior is the upstream-tested no-hardware state.
- **Done (139: gamepad normalization):** Standard layer (`aether.fingerprinting.gamepads`, default on): pages see an empty list via the same master/kill/exempt shape as the cores gate. Toggle in both settings with a breakage warning, row in our panel (gamepad icon) and the stock trust popup. Owns its registry entry and firefox default like other engines; the 135 keeps only its own sections (a bad splice once swallowed upper hunks into it; recovered by rebuilding the keeper from sync). Gates: empty list both ways on hardware-less boxes with no errors, 16 toggles with pref write, stock checkbox visually confirmed.
- **Done (138: media-device shield):** opt-in Strict layer (`aether.fingerprinting.mediaDevices`, default off with a disclaimer): pages see one generic device per listed kind with empty ids and per-origin group ids, pre-permission shape unchanged; prompts and capture keep working on the raw path. Owns its registry entry and firefox default like other engines. Toggle in both settings, row in our shields panel and the stock trust popup (mic icon), warning line in the device permission prompt on the trigger event. Gates: real hardware collapses to generics, group ids differ per origin, warning iff shield on, exempt via the proven helper.
- **Done (136: hamburger Settings opens the new settings menu):** the app-menu Settings entry now opens about:aethersettings via openTrustedLinkIn; only this entry is rerouted, every other openPreferences caller keeps the old page while the new menu is built. Gates: packaged panelUI.js verified carrying the reroute, headless smoke clean, about: regression loads; series OK (134 applied, 0 already there, 0 in conflict), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, MAR rebuilt with matching BuildID.
- **Done (127: coherent WebGL caps baseline, rare extensions hidden, WebGPU off):** renderer strings alone still let limits and extension lists describe the real GPU. Numeric caps report safe baselines when WebGL protection applies (texture/cube/renderbuffer 8192, uniform vectors 256, varyings 16, viewport 16384; single funnel at the numeric getParameter default plus the texture/viewport early sites, source limits untouched so internal allocation never sees them). Rare high-entropy extensions hidden in one place (IsSupported: WEBGL_debug_shaders leaks translated sources, WEBGL_provoking_vertex and OVR_multiview2 are Mozilla/VR-only tells; internal slots stay empty so dependent paths agree). dom.webgpu.enabled defaults off (adapter info bypassed everything, user-overridable). Debugging: member definitions cannot live in the anonymous-namespace block (it does not enclose the class); moz.build lists sort case-sensitively. Gates: caps-on (baselines exact, 3 hidden, keepers present, gpu absent, stable) and caps-off (real values back) PASS, link noise-on re-green; series OK (50 applied, 79 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (126: key noise on the top load, first-party exemptions only):** frame-origin keying let a tracker framed on several sites read identical noise everywhere (linkable). Noise keys now come from the propagated top-load key (generated per top document load when RFP leaves none, same inheritance pipe, cross-process included; reload re-keys by design), with legacy per-base keying only where no document exists (workers). Exemptions cover proven first-party reads only: no provable top means never exempt, so an exempted site cannot un-noise its own frames embedded elsewhere (workers keep explicit legacy exemption for compat; their values are constant anyway). Debugging: same-process top traversal returns null under fission (OOP frames), which is what exposed the frame-keying; RFP PNG encoder appends a per-load deBG metadata chunk fed by the new keys (harmless, carries no stable identifier), so the gate strips it before comparing encode bytes. New linkability gate (two tops plus the same tracker framed in both, 4 modes) supersedes the old peer-differs P1 gate. Gates: noise-on/control/masteroff/exempt PASS (tracker reads equal its top, differs across tops; exempt host raw with third parties still noised); series OK (49 applied, 78 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (110: fingerprinting signal registry):** new `toolkit/components/fingerprinting/signals.json` (no moz.build, build ignores the dir): 24 surfaces with verified `file:line` locations (40/40 machine-checked), RFP behavior noted for delimitation only, assigned policy + level + gate each, plus 2 recorded absences (deviceMemory, Client Hints) and the locked decisions. Contract for P1 canvas noise. Gates: series OK (43 applied, 65 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (111: deterministic canvas 2D read noise):** new `dom/canvas/AetherCanvasNoise` module (per-launch 32 B secret, SHA-256 stretched per first-party base domain, SplitMix64 pixel stream; blue LSB of pixel 0 + ~1/256) hooked into the single `GetImageDataArray` seam all 2D reads flow through, read-time only, display untouched. GC discipline: services before the cannot-GC region, pure integer pass after. Debugging found two real issues: `nsICryptoHash` is interface-only (use it, not the concrete header) and `NS_NewCryptoHash` already inits (second Init fails) - both diagnosed via temporary stderr probes, removed before sealing. Kill pref `aether.fingerprinting.canvasNoise2d` default on. Gates: two-origin harness PASS both ways (noise-on: stable + cross-differs; pref-off control: stable + identical, matching raw baseline), series OK (43 applied, 66 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (112: canvas encode-path noise):** `toDataURL`/`toBlob` both funnel through the owned packed-BGRA copy in `CanvasRenderingContext2D::GetImageBuffer` (verified: no display path uses it), so one hook with blue offset 0 covers both; module gains the channel-offset parameter (default keeps the 111 call site). Harness extended to digest all three read methods on both origins. Gates: all three methods stable + cross-differing with noise on, all identical with kill pref off; series OK (43 applied, 67 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (113: WebGL renderer strings + readback noise):** 8 coherent Windows triples (vendor/unmasked/masked, sanitizer-shaped) feed masked RENDERER, UNMASKED RENDERER and UNMASKED VENDOR from one per-site pick; masked VENDOR stays stock constant. RGBA8 readPixels gets the same keyed blue-LSB pass on the caller array. Module gains pref-parameterized key + SelectIndex; new webglNoise kill pref default on. Gates: renderer strings + readPixels stable/cross-differing/coherent with noise on (masked observed: GTX 980 triple), all identical with prefs off (control also proves stock masked output is coherent); series OK (43 applied, 68 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (114: WebAudio Analyser noise):** per-site noise on all four Analyser readout methods (float/bit, frequency/time), keyed like canvas/WebGL with its own audioNoise kill pref; noise lands on caller-owned arrays only, pure math inside cannot-GC, never on the audio path. `AudioBuffer.getChannelData` explicitly deferred (live shared reference: read-time noise would accumulate and go unstable/audible; needs render-time keying later). Module gains KeyForAudio + ApplyNoiseFloat. Debugging: float-freq reads are inherently unstable across calls even stock (smoothingTimeConstant blending) - harness sets it to 0 to test our layer, not the quirk; a stale Marionette instance on :2828 once poisoned a control run (kill scripts must match all ox-* profile patterns). Gates: analyser digests stable + cross-differing with noise on, all identical with prefs off; canvas/WebGL gates still green in the same run; series OK (43 applied, 69 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (115: common core count):** layer A begins, `Navigator.hardwareConcurrency` reports 8 behind its own kill pref (one seam, internal pool sizing unaffected in any breaking direction). Harness asserts navigator props on both origins. Gates: 8 everywhere with pref on (machine has 24), real identical count with it off, all previous gates still green in the same run; series OK (43 applied, 70 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (116: canvas measureText nudge):** reported width nudged by exactly one ulp, direction keyed per site+text (FNV-1a of the normalized text mixed into the domain stream); drawing untouched, layout impact ~1e-16. Module gains KeyForText/FNV1a/NudgeDouble; new textMetrics kill pref default on. Gates: widths stable + cross-differing with noise on, identical with it off, all previous gates still green; series OK (43 applied, 71 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (117: master kill-switch):** one pref gates the whole graded system (shared key helper + core-count normalization check it first), per-surface kills refine it; backend for the end-state UI (master + per-surface toggles). Default on. Gates: master-off run fully raw on every surface (cores back to 24, stock renderer), identical to the all-off control; series OK (44 applied, 71 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (118: buffer channel noise on first extraction):** stored AudioBuffer samples noised at most once, on first extraction, keyed by the extracting reader's site (later readers stable; CopyToChannel rewrites clear the key); detached shared storage never mutated, CopyFromChannel noises only its outgoing copy with absolute sample indexing. Harness digests rendered getChannelData on both origins. Debugging: analyser needed warmup reads (first post-render reads settle); stale-port trap resurfaced (kill patterns). Gates: buffer digests stable + cross-differing, all previous gates still green; series OK (44 applied, 72 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (119: per-site exceptions + renderer-space fix):** exact base-domain exempt prefs per surface or all surfaces, checked synchronously (backend for the broken-site switch). Its own gate caught a real defect: the 8-entry renderer table collides pairwise at p=1/8, so triples are now generated parametrically (family x model x PCI, ~800k combos, sanitizer-shaped, coherent). Separately, the first from-scratch gate-1 since 103 caught a latent series break: 105 carried a byte-identical duplicate of 02's syncedTabs.ftl deletion (proven mechanically, section dropped; regeneration impossible, states gone; backup kept at Temp/opencode/aether/105-backup.patch). Full series now applies clean from base and reproduces WORK 0/0/0. Gates: exempt origin reads raw baselines while the other stays noised; series from-scratch green, tree diff 0/0/0, TODO OK, build+package exit 0, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (120: Firefox UA compat token):** Google served its legacy basic-HTML page because our UA carries no Firefox token (only Aether/156.0.1). Flipped the upstream compat switch so HTTP and JS UAs read Firefox/156.0 alongside the honest Aether token; blends us with the Firefox anonymity set too. Stays user-overridable. Gates: packaged default true, runtime UA verified over Marionette, series OK (45 applied, 73 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (121: worker core count):** WorkerNavigator had its own HardwareConcurrency path leaking real cores in workers (caught live on CreepJS: window 8, workers 24). Same contract there, keyed by the worker principal; shared module gains the exported SiteExempted helper used by both Navigator call sites. Harness spawns a same-origin worker on both origins. Gates: 8/8 everywhere with prefs on, 24/24 agreeing with them off, exempt split respected; series OK (45 applied, 74 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (122: own shields panel):** the shield button opens our protections UI instead of the Firefox popup (XUL panelview, own controller, own Fluent copy, own `aether-*` CSS isolated for rebase and the future theme switch); ETP retired to custom/off with partitioning, query stripping and bounce protection kept. Visual pass: real panel-chrome variable names (`--panel-background-color/text/box-shadow`), violet toggle tokens, handmade icons moved from data-URIs (context-paint does not substitute there) to `chrome://` skin SVGs with context-paint, panel radius 14→10 with the shadow kept inside its margin room. Debugging: inline popup handlers die on CSP (listeners instead), headless screenshots skip layered popups (GDI needs CAPTUREBLT). Gates: series OK (46 applied, 75 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0, version string, headless smoke 0 chrome errors, headed screenshots verified light + dark, MAR rebuilt with matching BuildID.
- **Done (123: trust panel reroute):** the second site-info entry point (trust icon, "Aether is on guard") opens our shields panel too; old popups stay in tree unused. Gates: same series/tree/TODO/build/package/smoke/MAR as 122.
- **Done (124: block known fingerprinters from a vendored snapshot):** Disconnect open list (FingerprintingGeneral + FingerprintingInvasive, 556 domains, CC BY-NC-SA, static per-release snapshot, zero runtime list traffic) embedded in a new `toolkit/modules/AetherFingerprinterBlock.sys.mjs` system observer on `http-on-modify-request`, started from `BrowserGlue._beforeUIStartup`; cancels third-party listed loads only (first-party always passes, undeterminable fails open). Own master pref default on + test-only extra-hosts pref; own toggle at the top of Settings > Privacy & Security. Debugging: `Services` is a system-module global (importing it aborts startup and hangs Marionette sessions); `loadInfo.loadingDocument` is a Document, third-party proof needs `loadingPrincipal.asciiHost`. Gates: block-on (third-party script + frame blocked, first-party runs) and toggle-off (everything loads) PASS; series OK (47 applied, 76 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0, version string, headless smoke on about:preferences 0 chrome errors, MAR rebuilt with matching BuildID.
- **Done (125: stock Firefox UA):** the trailing \Aether/156.0.1\ token (~17 stable bits while our set is small) is off by default; \BuildUserAgent\ skips the app portion unless \general.useragent.showAppToken\ is true (any \general.useragent.*\ change rebuilds the UA live, so the toggle needs no restart). \ppVersion\ already reports the legacy stock value; platform/oscpu coherent; buildID is already a fixed value shared by all installs. Gates: stock UA byte-exact + coherence values PASS, opt-in tail PASS; series OK (48 applied, 77 covered, 0 conflicts), tree diff 0/0/0, TODO OK, build+package exit 0 with 0 warnings, version string, headless smoke 0 chrome errors, MAR rebuilt with matching BuildID.
- **Network silence of the setup has not been measured** end to end. The two
  earlier attempts failed and the connections that were seen belonged to
  `aether.exe` (launched by the stub at the end), not to the installer. A monitor
  restricted to `setup-stub` / `aether-full` would settle it.
- **`crash-tracker.py --self-test` is green again.** It went red after the squash (three checks looked
  for `124-` patches from the old numbering). The checks now assert the named patch exists and keeps
  the `NN-*` naming instead of a fixed number, plus a KB cross-reference (removed categories blamed,
  shipped categories not) — 15/15 OK.
- **`scripts/patch-sfx-stub.py` is repaired and in use**: paths are derived from `__file__` (plus
  `--src` for the worktree) instead of the old hardcoded machine paths, and it is what rewrites the
  icon/`VS_VERSIONINFO` in the prebuilt SFX module the user actually sees. Re-run it whenever the SFX
  or the icon changes.
- **Pending telemetry:** fresh grep decides - the 101/102/103 units exhausted every known candidate (sponsored attribution, DOM bindings, metric layer, fog/legacy gtests, doc trees). Scope each patch with a tree grep and check nothing still calls what is removed (patterns 89/92/96: the user pastes the runtime trace, the orphaned call site becomes its own patch).
- **Remaining telemetry:** the old work-group list is worked through: the wrapper call sites fell to
  patches 36–100 and the in-tree SDK self-metrics are gone. Explicitly still out of scope: the vendored
  `glean-core` internal metrics (`third_party/rust/glean-core`) and the application-services / mach /
  crashreporter pings. Stale docs may linger (e.g. `toolkit/components/telemetry/docs/data/install-ping.md`
  describes the removed install ping). What is left is scoped per patch by grepping the tree
  (`mozilla::glean` writers, `metrics.yaml`/`pings.yaml` definitions, `*Telemetry.*` call sites) —
  the standing rule ("clean it all, used or not") still applies to whatever the grep finds.
- **Release notes / homepage:** the four `app.releaseNotesURL*` prefs and
  `startup.homepage_override_url` point at the Pages site news page
  (`https://aethergroup.github.io/aether/news`).
- **Updater:** unsigned; Windows x64 only; no signed releases and no macOS.
- **Post-launch phase (only when the work is bugs + rebases):** Windows 7
  support via Win10+ API shims, Supermium-style. A project of its own, not
  now. Floor stays Windows 10 (Firefox 156 cannot start on 7 regardless of
  what the installer does).
- **The MAR in `Documents\aether-mar` is regenerated after every build** with `make-mar-local.py`
  (its `.buildid` sidecar must match the fresh `application.ini` BuildID) and `aus-local.py` answers
  from it: an older client BuildID gets OFFER, a current one gets empty `<updates></updates>`.
  Verified against the short `app.update.url` form (`/update/%VERSION%/%BUILD_ID%/update.xml`, owned
  by patch 01). Regenerate the MAR whenever the buildID changes.
- **Remote configured, nothing pushed**: `origin` =
  `https://github.com/AetherGroup/Aether-Browser.git` (public, still empty).
- *Local changelog:* retired in favour of the website (its repo is
  `AetherGroup/aether`, served with Pages). Its generator script too.
- **Future redesign with theme choice (planned, not now):** the browser UI
  will be redesigned, offering the user the current Firefox look or the new
  one. No rebase past 156.0.1 until Firefox 157 (Nova) is evaluated. Until
  then, all UI work stays isolated in own files/IDs/prefs (`aether-*`
  namespaced) so it survives a rebase and can later sit behind the theme
  switch.
- **Fingerprinting UX (locked, build at the end, not now):** every
  anti-fingerprinting option must be user-toggleable twice: one master
  button plus individual per-option toggles, so the user dials how much
  fingerprinting they accept. Per user decision; implement once the layers
  exist.
- **Settings direction (locked 2026-10-16, per user): no more work on stock
  `about:preferences`; only the new `about:aethersettings`.** Units
  170/172/173 (stock-only) were dropped from the series and their patch
  files deleted; 171 was trimmed to engine + new-settings UI
  (`AetherBlocker.sys.mjs`, `AetherSettingsDefs.sys.mjs`,
  `aethersettings.js/.css`, `firefox.js`). Backups in
  `%TEMP%\opencode\revert170-173-backup\`. End goal: port every remaining
  option to the new page, then delete `about:preferences` entirely.
- **Squash (2026-10-16, per user): 171 units compacted into 18 thematic
  groups** (`01-base-product` … `18-adblock-polish`, largest 9.5 MB).
  Method: scratch clone at base + one commit per unit (`C:\cr\sq`, kept
  while regrouping stays possible), each group regenerated as
  `git diff --no-renames --full-index --binary` between chain states —
  no line rewriting, so the final tree is identical by construction.
  Backup of the 171 files in `%TEMP%\opencode\presquash-backup\`.
  Re-proven: fresh apply 18/18 (scratch `C:\cr\g37`), old-vs-new tree
  compare 0/0/0, gate2 still green (worktree untouched).

---

## 10. Useful shortcuts

```powershell
# which patches touch a file?
git grep -l -- "diff --git a/netwerk/protocol/http/nsHttpChannel.cpp" patches

# list the pings/metrics that are left
git -C C:\fs grep -n "mozilla::glean" -- '*.cpp' | Select-Object -First 50

# what the stack touches, by file
Select-String -Path patches\core\*.patch -Pattern "diff --git a/<path> b/"

# repo state
git status --short
git log --oneline -10
```
