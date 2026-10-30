# Building Aetherfox

The authoritative guide to building Aetherfox from source. If a step is not here,
it does not work.

For what Aetherfox is and what it removes, see the [README](../README.md).

> **Pre-release software.** Builds run on Windows x64. Binaries are not
> code-signed. [Aetherfox 0.1](https://github.com/AetherGroup/Aetherfox/releases/tag/v0.1)
> is out (offline setup + portable zip); there is still no public update server.

- [Quick start](#quick-start)
- [Requirements](#requirements)
- [Install](#install)
- [Build](#build)
- [Verify](#verify)
- [The patch stack](#the-patch-stack)
- [Disk usage](#disk-usage)
- [Faster iteration](#faster-iteration)
- [Troubleshooting](#troubleshooting)
- [For contributors](#for-contributors)

## Quick start

For a machine that has never built Firefox before, expect 40 to 60 minutes of
setup and one to three hours of compilation.

```powershell
# Layout matters: keep both the repository and the source tree short.
# See "Choose a short source path" below before deviating from this.
New-Item -ItemType Directory -Force C:\o\browser
cd C:\o\browser
git clone https://github.com/AetherGroup/Aetherfox .

# No bundled extensions since 150: blocking is integrated natively, so there
# is nothing to download into third_party/.

# Clones Firefox, fetches the build toolchains, applies the patch stack.
python scripts\sync.py --src C:\o\fs --apply --no-download

# Then compile and package.
$env:MOZCONFIG = "C:\o\browser\mozconfig.windows"
scripts\windows\run-build.cmd
scripts\windows\run-package.cmd
python scripts\verify-flags.py --objdir C:\o\fs\obj-aether
C:\o\fs\obj-aether\dist\bin\aether.exe --version
```

That last command must print:

```
Aether Aetherfox 156.0.1
```

`run-bootstrap.cmd` also has to run once per machine, after installing
Visual Studio Build Tools and MozillaBuild. See [Install](#install).

## Requirements

Verified on this exact combination. Other versions may work but are not tested.

| Component | Version | Notes |
|---|---|---|
| Windows | 11 x64, build 26100 | the account name must not contain spaces |
| Visual Studio Build Tools | 17.14.37710, MSVC 14.44.35207 | headers and import libraries only, see below |
| MozillaBuild | 4.2.1 | installs to `C:\mozilla-build` |
| Git | 2.55 or newer | with `core.longpaths=true` |
| Python | 3.12 | 3.13 works but warns about an unknown version |
| Rust | 1.99.0 | installed by `mach bootstrap` |
| clang-cl | from Mozilla's Taskcluster | lands in `~/.mozbuild/clang/bin` |
| cbindgen | 0.29.4 | `cargo install cbindgen --locked` |
| nasm | 2.16.03 | 2.16 or newer |
| CPU | 8 cores minimum | compilation scales with cores |
| RAM | 16 GB | 32 GB or more is much more comfortable |
| Disk | 60 GB free | see [Disk usage](#disk-usage) |

Visual Studio Build Tools is still required even though clang-cl does the
compiling: it provides the Windows SDK and the C++ headers and import
libraries that clang-cl compiles against.

### What `mach bootstrap` does not do on Windows

Expect this to trip people up, because the bootstrap reports success and
installs nothing useful.

1. **It installs Rust and nothing else.** mozboot's Windows bootstrapper only
   calls `pacman_install`, and MozillaBuild 4.x no longer ships `pacman`. The
   run ends with *"Your system should be ready to build Firefox for Desktop!"*
   and exit code 0.
2. **The compiler toolchains are not fetched on release tags.** In
   `build/moz.configure/bootstrap.configure`, `--enable-bootstrap` only defaults
   to on for nightly checkouts:

   ```python
   def bootstrap_default(vcs_checkout_type, is_nightly, automation):
       if automation:
           return False
       if is_nightly and vcs_checkout_type:
           return True
   ```

   Aetherfox pins `FIREFOX_156_0_1_RELEASE`, a release, so configure then fails
   with `ERROR: Cannot find the target C compiler`.
3. **The toolchain taskgraph hashes files that Aetherfox deletes.** Fetching a
   toolchain runs `mach taskgraph tasks`, which digests files named by the task
   definitions. Two of them do not exist in an Aetherfox tree: everything under
   `mobile/`, which `sync.py` removes before applying the stack, and a crash
   reporter test file that the patches delete. So toolchains can only be fetched
   from a pristine checkout.

`scripts/sync.py` handles all of this in its `ensure_toolchains` step, which runs
before it touches the source tree. You should never have to deal with it
manually. It exists here so the failure modes are documented rather than
discovered.

## Install

### 1. Visual Studio Build Tools

Administrator required. Get the bootstrapper from
<https://aka.ms/vs/17/release/vs_BuildTools.exe>, then:

```powershell
.\vs_BuildTools.exe --quiet --wait --norestart --nocache `
  --installPath "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools" `
  --add Microsoft.VisualStudio.Workload.VCTools `
  --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
  --add Microsoft.VisualStudio.Component.Windows11SDK.26100 `
  --add Microsoft.VisualStudio.Component.VC.ATL
```

Verify afterwards:

```powershell
& "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe" -products * -property installationPath
```

If that prints a path ending in something other than
`2022\BuildTools`, the installer was given an unquoted path and split it at the
space. Reinstall with `--installPath` as a single quoted argument, as above.

### 2. MozillaBuild

```powershell
Invoke-WebRequest -Uri https://ftp.mozilla.org/pub/mozilla/libraries/win32/MozillaBuildSetup-Latest.exe -OutFile MozillaBuildSetup-Latest.exe
.\MozillaBuildSetup-Latest.exe /S
```

Accept the default location, `C:\mozilla-build`. If you install it elsewhere,
set `MOZILLABUILD` before running the wrapper scripts.

### 3. Git and Python

No administrator needed:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
git config --global core.longpaths true
```

`core.longpaths` is required. Firefox tracks files whose names are long enough
to exceed `MAX_PATH`, and without it `git clone` fails with
`Filename too long`. It fixes git, not the build: see
[Choose a short source path](#build).

### 4. nasm

Needed for AV1, VPX and JPEG.

**Do not install nasm with winget.** `NASM.NASM` reports a successful install,
but registers no package and leaves no `nasm.exe` anywhere, so
`winget list` shows nothing and configure still fails with
`ERROR: Nasm is required to build with AV1, FFVPX, JPEG and VPX`.

Install it manually:

```powershell
New-Item -ItemType Directory -Force C:\tools
Invoke-WebRequest -Uri https://www.nasm.us/pub/nasm/releasebuilds/2.16.03/win64/nasm-2.16.03-win64.zip -OutFile nasm.zip
Expand-Archive nasm.zip -DestinationPath .\nasm-x
Copy-Item .\nasm-x\nasm-2.16.03\* C:\tools\nasm -Recurse -Force
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User").TrimEnd(';') + ";C:\tools\nasm", "User")
```

Confirm with `nasm -v`.

### 5. Rust, and the `mach` environment

Once per machine, about 20 minutes:

```powershell
scripts\windows\run-bootstrap.cmd
```

This installs the Rust toolchain, creates the `mach` virtualenvs, and offers to
add Microsoft Defender exclusions. Accept the exclusions: without them every
object file the build produces gets scanned and the build slows to a crawl. If
you decline, the step is not retried unless you delete
`~\.mozbuild\.ANTIVIRUS_EXCLUSIONS_DONE`.

### 6. cbindgen

```powershell
cargo install cbindgen --locked
```

## Build

### Choose a short source path

This is not optional, and it is the most common reason a build that looks fine
fails hours in.

Firefox ships test fixtures with roughly 140-character filenames, and mozmake
silently loses track of inputs once absolute paths pass about 224 characters.
The symptom is a bogus `No rule to make target` while linking `libxul`, long
after compilation has finished.

This is an upstream problem, not an Aetherfox one, and the chain is documented:

- Windows caps a path at `MAX_PATH`, 260 characters.
- Upstream budgets right up to that limit. Firefox's own `configure.py` has
  `WIN32_MAX_PATH = 260`, `LONGEST_KNOWN_OBJDIR_RELATIVE_PATH = 170` and
  `DEFAULT_OBJDIR_NAME_LEN = 28`, which works out to **a 62-character limit for
  the source directory**, above which it refuses to configure. Its recommended
  layout is `D:\mozilla-source\firefox` (26 characters) and its CI uses
  `z:\build\workspace`.
- Where the ceiling lands depends on the `mozmake.exe` and the MSVC that built
  it, so it has to be measured, not quoted. On this machine mozmake resolves
  existing files at up to 255 characters. Mozilla's CI hit the bug at 76
  (bug 1712350, `stat: ... Unknown error` followed by `No rule to make
  target`), traced to GNU make bug 58656, which MozillaBuild patches in
  `make-mozmake.sh`.

What matters is the longest path the build actually touches, and that is not
the longest path in the tree. The test262 fixtures reach 214 characters, but
they are test data and never enter the build graph: this build walks
`testing/web-platform` and completes with them sitting right there. Build
outputs top out at **170 characters relative to the objdir**, which is exactly
upstream's `LONGEST_KNOWN_OBJDIR_RELATIVE_PATH`.

Measured on this tree, with test data excluded:

| Source path | Prefix | Longest build-relevant path | Margin |
|---|---|---|---|
| `C:\o\fs\` | 8 | 184 | 39 |
| `C:\aether-156\` | 14 | 190 | 33 |
| `D:\mozilla-source\firefox\` | 26 | 202 | 21 |

Only the source tree has to be short. The repository itself can sit anywhere,
because the build never puts a repository path into the link. Upstream's own
62 character limit for the source directory leaves plenty of room, so use a
name that means something: `C:\aether-156`, and `C:\aether-157` after the
rebase. Renaming on a rebase costs nothing, because a rebase changes thousands
of files and the objdir has to be rebuilt either way.

`sync.py` measures this and fails on the spot, rather than letting the build
die at the link 40 minutes later:

```
[aether] path budget: prefix 7 chars, longest path 221 chars (limit 223)
```

If it goes over, the message says how many characters you have to shave off
and where. Do not skip it with `--skip-path-check`.

### The wrapper scripts and short source paths

By default the wrappers in `scripts/windows/` look for the source tree in
`..\firefox-src`, relative to the repository. Any path ending in `\firefox-src\`
is too long for the build, as the table above shows, so the default can never
satisfy both requirements at once.

Point them somewhere else with the `FIREFOX_SRC` environment variable:

```powershell
$env:FIREFOX_SRC = "C:\fs"
$env:MOZCONFIG  = "C:\o\browser\mozconfig.windows"
scripts\windows\run-build.cmd
```

Without it, call `mach` directly, as shown in [Configure](#configure).

### Fetch Firefox and apply the patch stack

```powershell
python scripts\sync.py --src C:\o\fs --apply --no-download
```

This clones the tag in `firefox_version.txt`, fetches the missing build
toolchains, removes `mobile/`, applies the patch stack and copies the
branding assets. No staged binaries: distribution carries only
distribution.ini.

Expected output:

```
[aether] toolchains: already installed in C:\Users\<you>\.mozbuild
[aether] 18 applied, 0 already there, 0 in conflict
[aether] branding assets: 55 gaps filled from unofficial, 35 Aetherfox files
[aether] distribution: carried by the series (no staged binaries)
[aether] sync OK
```

`--apply` is not optional. Without it, `sync.py` only checks that the series is
coherent and leaves the checkout as plain Firefox, so you would go on to compile
upstream.

Pass `--skip-toolchains` if the machine is already provisioned or has no
network access.

### Configure

```powershell
$env:MOZCONFIG = "C:\o\browser\mozconfig.windows"
scripts\windows\run-configure.cmd
```

`MOZCONFIG` is not optional either. Without it you build the `unofficial`
branding into the wrong objdir, and none of the Aetherfox patches take effect.

The wrapper scripts locate the source tree as a sibling of the repository, so
they expect `C:\o\browser` and `C:\o\fs`. If you used a different `--src`, call
`mach` directly:

```powershell
C:\mozilla-build\start-shell.bat -no-start -defterm -c "cd /c/o/fs && MOZCONFIG=/c/o/browser/mozconfig.windows MACH_HIDE_DEV_DRIVE_SUGGESTION=1 python3 mach --no-interactive configure"
```

### Compile

```powershell
scripts\windows\run-build.cmd
```

One to three hours from scratch on 12 cores; a few minutes for an incremental
build afterwards. The output is long, so redirect it to a file rather than
paging through it.

## Verify

### Privacy check on the build output

```powershell
python scripts\verify-flags.py --objdir C:\o\fs\obj-aether
```

Must print `TODO OK` and exit 0.

### Package and the installer

```powershell
scripts\windows\run-package.cmd
python scripts\build.py --src C:\o\fs --package-only
```

`mach package` produces the portable zip plus the full NSIS installer and the
stub (`MOZ_STUB_INSTALLER=1` in the mozconfig). `scripts/build.py` then packs
both into the single-file offline setup with `make-stub-offline.py` and
deletes the standalone installers from `dist`, so it installs with no
network: `obj-aether/dist/` ships `AetherfoxSetup-<version>.exe` (~85 MB),
the zip, and small metadata. It also fails if the uninstaller is missing
from the package (`uninstall/helper.exe`, which the updater runs after
every update), and `verify-flags.py` fails the build on any privacy
regression. `installer/` still holds the retired .NET/Avalonia sources;
nothing builds them.

### Smoke test

```powershell
C:\o\fs\obj-aether\dist\bin\aether.exe --version
```

Must print `Aether Aetherfox 156.0.1`. Then confirm that *About Aetherfox* shows the
Aetherfox wordmark and the version rather than Firefox, and that
*Settings → Optional Features* exists with Report Broken Site off.

## The patch stack

The patches are the source of truth. Nothing proprietary, no hidden code path.

```
firefox_version.txt      pinned upstream tag
patches/series           application order, 19 thematic groups
patches/core/*.patch     the changes
branding/                name, icons, about dialog
defaults/prefs/          sealed preferences
scripts/                 sync, build, package, updater tooling
```

Firefox is public, so anyone can reproduce the exact browser:

```powershell
git clone https://github.com/AetherGroup/Aetherfox
cd Aetherfox
python scripts/sync.py --apply
python scripts/build.py
```

`mobile/` is deliberately removed from the checkout rather than deleted by a
patch: encoding the removal of about 15,000 files as a diff would cost 127 MB
of patch. It is desktop-only code and none of it compiles or ships on Windows.
Because the taskgraph in step 5 of `sync.py` digests files that live under
`mobile/`, the toolchains are fetched before that removal happens.

## Disk usage

The 60 GB figure is not padding. A full build needs all of this simultaneously:

| What | Size |
|---|---|
| Firefox snapshot, cloned with `--depth 1` | 4.4 GB, of which `.git` is 1.0 GB |
| `obj-aether`, the build output | 15 to 20 GB |
| `~\.mozbuild`, the toolchains | 5 to 8 GB |
| Rust toolchain in `~\.rustup` and `~\.cargo` | 2 to 3 GB |
| Visual Studio Build Tools | 3 GB |

The complete Firefox history is around 30 GB and is deliberately not
downloaded: `sync.py` clones with `--depth 1`, so `.git` stays at 1 GB. The
history of what Aetherfox changed lives in the patch stack, not in the Firefox
repository.

## Faster iteration

For UI and preferences work, uncomment this in `mozconfig.windows`:

```
ac_add_options --enable-artifact-builds
```

and build with `mach artifact install`. It downloads prebuilt binaries from
Mozilla instead of compiling, so a build takes minutes.

Artifact builds do not produce an Aetherfox binary for verification: the artifacts
are stock Firefox. The privacy check and the smoke test are meaningless in
artifact mode.

## Troubleshooting

### `ERROR: Cannot find the target C compiler`

clang-cl is missing. Confirm `~\.mozbuild\clang\bin\clang-cl.exe` exists. If it
does not, run `sync.py` without `--skip-toolchains`, or fetch it by hand as
described in the contributor notes below.

### `FileNotFoundError: ... mobile/android/android-components/build.gradle`

or `... toolkit/crashreporter/test/browser/browser_aboutCrashesResubmit.js`

The toolchain fetch was attempted on an Aetherfox tree, and the taskgraph needs
files that Aetherfox deletes. Reset the checkout to pristine first, or let
`sync.py` do it for you.

### `ERROR: Cannot find cbindgen`

`cargo install cbindgen --locked`.

### `ERROR: Nasm is required to build with AV1, FFVPX, JPEG and VPX`

nasm is not on `PATH`. See [nasm](#4-nasm). A silent `winget install NASM.NASM`
is not enough.

### `ERROR: Windows App SDK dir not present!`

The `winappsdk-x86_64-pc-windows-msvc` toolchain is missing.

### `ERROR: Cannot find wasi headers or problem with the wasm compiler`

The `sysroot-wasm32-wasi` toolchain is missing. Configure offers
`--without-wasm-sandboxed-libraries` as an alternative; it is not a substitute,
because it gives up sandboxed parsing of fonts and media.

### `error: browser/branding/aether/...: already exists in working directory`

The patch stack creates those files, so they must not be present when it is
applied. Resetting the tree by hand leaves untracked files behind, because a
reset does not remove them:

```powershell
git -C C:\o\fs clean -fd      # leaves gitignored objdirs alone
git -C C:\o\fs checkout -- .
```

Note that `sync.py` prints only the last line of git's stderr, so this error
can surface as something unrelated. Read the full output when a patch conflicts
unexpectedly.

### `No rule to make target` while linking libxul

Path length. See [Choose a short source path](#choose-a-short-source-path).

### `mach: command not found`

Run from a MozillaBuild shell, `C:\mozilla-build\start-shell.bat`, or use the
wrapper scripts in `scripts\windows\`.

### `unable to open output file '-'` during the build

An sccache flake. sccache is disabled in `mozconfig.windows` on purpose; do not
re-enable it.

### `Bootstrap support for Windows is under development`

Expected. `mach bootstrap` does not support Windows; that is what MozillaBuild
and `run-bootstrap.cmd` are for.

### `stty: 'entrada estándar': Inappropriate ioctl for device`

Harmless. It appears whenever a wrapper runs without an attached terminal.

### The build is very slow

Microsoft Defender exclusions were declined. See
[Rust, and the mach environment](#5-rust-and-the-mach-environment).

### Reporting a problem

Include these, because almost every report turns out to be one of them:

- the exact error line, and the surrounding output of the failing step
- output of `nasm -v`
- whether `~\.mozbuild\clang\bin\clang-cl.exe` exists
- output of `git --version` and `python --version`
- your source path, and the length of its longest file name

## For contributors

### Verification gates

All five must pass before committing a change.

| # | Gate | How |
|---|---|---|
| 1 | Series applies on the base commit | `python scripts\sync.py --apply` |
| 2 | Stack rebuilds the entire tree | clean-clone comparison, below |
| 3 | Build privacy defaults | `python scripts\verify-flags.py --objdir <objdir>` |
| 4 | Compiles and packages | `python scripts\build.py` |
| 5 | Binary starts | `aether.exe --version` |

Gate 1 is structurally blind: it only checks that each patch fits the tree in
front of it. If a file drops out of the stack, gate 1 stays green while a clean
clone silently keeps the upstream version, and the failure shows up much later
as a compile error or a browser that still phones home. Gate 2 compares the
whole tree and is the one that catches it.

```powershell
git clone --shared --no-checkout C:\o\fs C:\cr\t
git -C C:\cr\t checkout -f 19a90052d7869f7b194ff27d316520366ad1d592
python scripts\sync.py --src C:\cr\t --apply --no-download
```

Then compare `git status --porcelain --untracked-files=all` in both trees. The
file lists must match and every common file must be byte-identical. Expect
18,562 touched files in both trees, 0 exclusive, 0 differing (measured on
156.0.1 + the 18-group stack; ~15,019 of those are the `mobile/` deletions
performed by `sync.py`, the rest is the stack plus the copied branding
assets).

`git clone --shared` reuses the objects of the existing repository, so it takes
seconds instead of downloading gigabytes.

### Fetching toolchains by hand

Only for `--skip-toolchains` and for debugging. The checkout must be pristine,
because the taskgraph digests files that the stack deletes.

```powershell
git -C C:\o\fs clean -fd
git -C C:\o\fs checkout -- .

C:\mozilla-build\start-shell.bat -no-start -defterm -c `
  "cd /c/o/fs && MACH_HIDE_DEV_DRIVE_SUGGESTION=1 python3 mach --no-interactive configure --enable-bootstrap=no-update"

git -C C:\o\fs clean -fd
git -C C:\o\fs checkout -- .

python scripts\sync.py --src C:\o\fs --apply --no-download
```

`--enable-bootstrap=no-update` enables every toolchain and skips the ones
already installed, so it is safe to re-run. To fetch exactly one:

```
--enable-bootstrap=clang
--enable-bootstrap=sysroot-wasm32-wasi
--enable-bootstrap=winappsdk-x86_64-pc-windows-msvc
```

An empty `--enable-bootstrap` fetches nothing, because `want_bootstrap()`
returns False when the option has no names. That is why `mach bootstrap` can
appear to succeed while installing nothing.

### Update channel

Builds use the `aether-release` channel declared in `mozconfig.windows`, pinned
with `--with-update-channel`, `MAR_CHANNEL_ID` and
`ACCEPTED_MAR_CHANNEL_IDS`. The last one is what makes the updater accept a MAR
that does not come from a Mozilla channel.

MARs are unsigned, which is why the build passes
`--enable-unverified-updates`. During development they are produced by
`scripts/make-mar-local.py` and served by `scripts/aus-local.py`, which compares
the client's `BUILD_ID` against the MAR's and answers `<updates></updates>` when
the build is already current, because `mach update serve` would otherwise offer
the same update on every start. There is no public update server.

**The browser never checks on its own.** The update check starts only when the
user asks for it (Help > About, or Preferences > "Check for updates"), the
update is offered, and only the user starts the download and the install. That
is enforced in code, not in configuration: `UpdateService.manualUpdateOnly` is
unconditionally `true`, the service does not check when it resumes, and
`UpdateUtils.getAppUpdateAutoEnabled()` always returns `false` so neither the
per-installation `update-config.json` nor the upstream `app-auto-updates-*`
policies can turn automatic updates on (patch 17).

To test the whole flow locally:

```sh
python scripts/make-mar-local.py --srcdir <src>/obj-aether/dist/aether \
    --out C:/aether-mar/aether-156.0.1.complete.mar \
    --version 156.0.1 --channel aether-release
python scripts/aus-local.py --dir C:/aether-mar \
    --mar aether-156.0.1.complete.mar --port 8000
```

Then click "Check for updates" in the browser. Note that `app.update.auto` is
**per installation** on Windows (`C:\ProgramData\Mozilla-<guid>\updates\<hash>\
update-config.json`), not a profile pref, and that with the current code it
cannot switch automatic updates on any more.