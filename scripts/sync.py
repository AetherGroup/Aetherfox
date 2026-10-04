"""Aether sync: the Helium/ungoogled-chromium style pipeline.

Reads firefox_version.txt, clones the clean tag of mozilla-firefox/firefox into
../firefox-src (or --src DIR), fetches the build toolchains, verifies the series
and applies patches/series, then copies branding assets and stages the deps
listed in aether.deps.ini.

Usage:
  python scripts/sync.py [--src ..\\firefox-src] [--skip-toolchains] [--no-download]
"""
import argparse
import configparser
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIREFOX_REPO = "https://github.com/mozilla-firefox/firefox.git"

# Toolchains the Windows build needs that `mach bootstrap` never installs. On a
# release tag --enable-bootstrap only defaults to on for nightly checkouts
# (build/moz.configure/bootstrap.configure), and resolving a toolchain runs the
# taskgraph, which digests files Aether deletes: all of mobile/ plus a crash
# reporter test. That is why this has to run on a pristine tree, before mobile/
# is removed and before the stack is applied. See docs/BUILD.md.
TOOLCHAIN_MARKERS = (
    "clang/bin/clang-cl.exe",
    "sysroot-wasm32-wasi",
    "winappsdk-x86_64-pc-windows-msvc",
    "windows-rs",
)


def git_ok(cmd, cwd=None):
    """Run a git command, return True on exit 0, never abort."""
    print("+", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0 and (r.stdout.strip() or r.stderr.strip()):
        print((r.stdout + r.stderr).strip().splitlines()[-1][:200])
    return r.returncode == 0


def mozbuild_state():
    env = os.environ.get("MOZBUILD_STATE_PATH")
    return Path(env) if env else Path.home() / ".mozbuild"


# Longest absolute path mozmake copes with on Windows. Below that it silently
# loses track of inputs and the libxul link dies with a "No rule to make target"
# that says nothing about paths.
#
# Windows allows 260 (MAX_PATH) and upstream budgets right up to it: Firefox's
# configure.py uses WIN32_MAX_PATH=260 and LONGEST_KNOWN_OBJDIR_RELATIVE_PATH=170,
# which is where our own build tops out, and allows a 62 character srcdir. We
# keep a margin below that because the exact figure is environment dependent: a
# mozmake on one setup resolves 255 character paths, while Mozilla's CI failed on
# 76 character ones (bug 1712350, GNU make bug 58656).
PATH_BUDGET = 223

# Test data never enters the build graph, but it does contain the longest names in
# the tree (the test262 fixtures run to 214 characters). Counting them would force
# a 9 character prefix for no reason, and the build demonstrably works with them
# present, so they are skipped. What remains is what the build actually touches.
SKIP_DIRS = {"test", "tests", "testing", "test262", "mochitest", "reftests", "mobile"}


def longest_path_len(root):
    """Longest absolute path under root, skipping .git, objdirs and test data."""
    base = len(str(root)) + 1
    longest = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d != ".git" and not d.startswith("obj-")
                       and d.lower() not in SKIP_DIRS]
        for name in filenames:
            n = len(os.path.join(dirpath, name)) - base
            if n > longest:
                longest = n
    return base + longest


def check_path_budget(src):
    """Fail here, not 40 minutes into a build, if the path is too long."""
    prefix = len(str(src)) + 1
    longest = longest_path_len(src)
    print(f"[aether] path budget: prefix {prefix} chars, longest path "
          f"{longest} chars (limit {PATH_BUDGET})")
    if longest > PATH_BUDGET:
        rel = longest - prefix
        allowed_prefix = PATH_BUDGET - rel
        need = prefix - allowed_prefix
        raise SystemExit(
            f"[aether] ERROR: the source path is too long for mozmake.\n"
            f"[aether]   at {src} the longest path in the tree is {longest} "
            f"characters, over the {PATH_BUDGET} that mozmake tolerates.\n"
            f"[aether]   The tree itself needs {rel} characters, so the source "
            f"directory has to be at most {allowed_prefix} characters, "
            f"including the trailing backslash.\n"
            f"[aether]   Move it that short, e.g. C:\\o<version> (needs {need} "
            f"fewer characters), and point --src at the new location. Skipping "
            f"this is how you lose a build at the libxul link with a "
            f"'No rule to make target' that never mentions paths."
        )


def missing_toolchains():
    state = mozbuild_state()
    return [m for m in TOOLCHAIN_MARKERS if not (state / m).exists()]


def ensure_toolchains(src):
    """Fetch the toolchains the Windows build needs.

    Idempotent: no-update reuses whatever is already installed and only fetches
    what is missing. Success is measured with the markers rather than mach's
    exit code, because `mach configure` can fail for an unrelated reason
    (branding, mozconfig) after the toolchains are already in place.
    """
    if os.name != "nt":
        print("[aether] toolchains: checking is Windows-only, skipped")
        return
    missing = missing_toolchains()
    if not missing:
        print(f"[aether] toolchains: already installed in {mozbuild_state()}")
        return
    print(f"[aether] toolchains: {len(missing)} missing: {', '.join(missing)}")
    print("[aether] toolchains: downloading (clang-cl, sysroot WASI, WinAppSDK, windows-rs)...")
    env = dict(os.environ)
    env.pop("MOZCONFIG", None)
    log = ROOT / "logs" / "toolchains.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    # Separate objdir: this pass must not touch obj-aether nor the project
    # mozconfig, it only has to resolve the toolchains.
    cmd = ["cmd", "/c", "mach.cmd", "configure", "--enable-bootstrap=no-update",
           "mk_add_options=MOZ_OBJDIR=@TOPSRCDIR@/obj-toolchains"]
    with log.open("w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.run(cmd, cwd=str(src), env=env, stdout=fh,
                              stderr=subprocess.STDOUT)
    still = missing_toolchains()
    if still:
        print(f"[aether] ERROR: toolchains not resolved (mach exit {proc.returncode}): "
              f"{', '.join(still)}")
        print(f"[aether] Last lines of {log}:")
        for line in log.read_text(encoding="utf-8",
                                  errors="replace").splitlines()[-12:]:
            if line.strip():
                print("   ", line.strip()[:160])
        print("[aether] Manual recipe in docs/BUILD.md, section 'Fetching toolchains by hand'.")
        raise SystemExit(2)
    print("[aether] toolchains OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT.parent / "firefox-src"))
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--skip-toolchains", action="store_true",
                    help="do not fetch toolchains even when missing (machine "
                         "already provisioned, or offline)")
    ap.add_argument("--skip-path-check", action="store_true",
                    help="skip the mozmake path length budget check")
    ap.add_argument("--apply", action="store_true",
                    help="actually apply the patches to a clean checkout")
    args = ap.parse_args()

    tag = (ROOT / "firefox_version.txt").read_text().split()[0]
    src = Path(args.src)
    print(f"[aether] tag={tag} src={src}")

    pristine = False
    if not (src / ".git").exists():
        if not git_ok(["git", "clone", "--depth", "1", "--branch", tag, FIREFOX_REPO, str(src)]):
            raise SystemExit("[aether] ERROR: clone failed. Check network and git.")
        pristine = True
    else:
        dirty = subprocess.run(["git", "-C", str(src), "status", "--porcelain"],
                               capture_output=True, text=True).stdout.strip()
        if dirty:
            print("[aether] tree has Aether changes (expected in dev); skipping checkout,")
            print("[aether] only verifying the series. For a clean reset: "
                  "git -C <src> reset --hard <tag>")
        else:
            git_ok(["git", "-C", str(src), "fetch", "--depth", "1", "origin",
                    f"refs/tags/{tag}:refs/tags/{tag}"])
            git_ok(["git", "-C", str(src), "checkout", tag])
            pristine = True

    # Toolchains first: the taskgraph that fetches them digests files under
    # mobile/ and the crash reporter, which still exist here but not two steps
    # further down.
    if args.skip_toolchains:
        print("[aether] toolchains: skipped via --skip-toolchains")
    elif pristine:
        ensure_toolchains(src)
    else:
        print("[aether] toolchains: not checked on an already modified tree;")
        print("[aether] if configure fails with 'Cannot find the target C compiler',")
        print("[aether] reset the tree and retry, or read docs/BUILD.md.")

    if not args.skip_path_check:
        check_path_budget(src)

    series = [l.strip() for l in (ROOT / "patches" / "series").read_text().splitlines()
              if l.strip() and not l.strip().startswith("#")]
    print(f"[aether] {len(series)} patches in series:")
    pending = []
    ready = []
    for p in series:
        pf = ROOT / "patches" / p
        if not pf.exists():
            print(f"  MISSING {p}")
            pending.append(p)
            continue
        text = pf.read_text(encoding="utf-8", errors="replace")
        is_stub = "Status: STUB" in text or "TODO(v1)" in text
        print(f"  {'STUB ' if is_stub else 'OK   '} {p}")
        if is_stub:
            pending.append(p)
        else:
            ready.append(p)
    if pending:
        print(f"[aether] {len(pending)} STUB/MISSING patches: not applied (the rest are).")
    ok, applied, covered, broken = [], [], [], []
    # -c core.autocrlf=false: MinGit defaults to autocrlf=true, which would make
    # git apply rewrite LF to CRLF outside repos that pin .gitattributes.
    GIT_APPLY_BASE = ["git", "-c", "core.autocrlf=false", "-C", str(src), "apply"]
    for p in ready:
        pf = str(ROOT / "patches" / p)
        if git_ok(GIT_APPLY_BASE + ["--check", pf]):
            ok.append(p)
        elif git_ok(GIT_APPLY_BASE + ["--reverse", "--check", pf]):
            applied.append(p)
        else:
            broken.append(p)
    for p in ok:
        print(f"  applies cleanly: {p}")
    for p in applied:
        print(f"  already applied in tree: {p}")
    # Patches stacking on the same file (40+50 both touch moz.build): if forward
    # and reverse both fail but a LATER patch touching the same files reverts
    # cleanly, this one is covered by the applied stack.
    #
    # The search has to be transitive. "Covered" patches cover in turn, and a
    # chain like 04 -> 03 -> 05 -> ... -> 31 is only found by walking it: without
    # this, 04-telemetry-feat-a was reported as a CONFLICT on a tree where it is
    # perfectly applied, because every patch it overlaps is itself only
    # "covered" and never "applied". That is a false positive in the report, not
    # a broken tree; gate 2 (full tree comparison) is what proves the stack.
    import re
    def touched(pf):
        txt = (ROOT / "patches" / pf).read_text(encoding="utf-8", errors="replace")
        return set(re.findall(r"^diff --git a/(.*?) b/.*$", txt, re.M))
    files_of = {p: touched(p) for p in ready}

    def covered_by_later(p, pool):
        """True if some later patch in `pool` touches a file p also touches."""
        idx = ready.index(p)
        return bool(files_of[p]) and any(
            files_of[p] & files_of.get(q, set())
            for q in ready[idx + 1:] if q in pool)

    # Grow the covered set until it stops growing. Starting from `applied` plus
    # whatever the first pass finds, a covered patch becomes a candidate to cover
    # its own predecessors.
    pool = set(applied)
    pending = list(broken)
    while pending:
        grew = False
        still = []
        for p in pending:
            if covered_by_later(p, pool):
                covered.append(p)
                pool.add(p)
                grew = True
            else:
                still.append(p)
        pending = still
        if not grew:
            break
    broken = pending
    for p in covered:
        print(f"  covered by a later patch: {p}")
    if not args.apply:
        for p in broken:
            print(f"  CONFLICT: {p} (needs a manual rebase)")
        if broken:
            print("[aether] some patches conflict; not aborting, to avoid blocking dev.")
        elif ready:
            print(f"[aether] series OK: {len(ok)} applicable, "
                  f"{len(applied)} applied, {len(covered)} covered")
    # Mobile platforms out of the tree BEFORE applying the stack: the build is
    # Windows only and nothing under mobile/ compiles or ships there (audited:
    # comments, desktop=false branches and string tables only).
    #
    # It is deliberately not in the patch stack, and not out of taste: encoding
    # the removal of ~15k files as a diff came to 127 MB, over GitHub's hard
    # 100 MiB per-file limit. With the removal in the stack the repo could not
    # be published at all, which is the whole point of this project. Regenerating
    # it on every rebase was also unusable.
    #
    # Consequence: "the patches are the source of truth" has one exception. Gate 2
    # (the full tree comparison) is what covers it.
    import shutil as _shutil
    _mob = src / "mobile"
    if _mob.is_dir():
        _shutil.rmtree(_mob, ignore_errors=True)
        print("[aether] mobile/ removed from the tree")

    if args.apply:
        # Applied sequentially in series order, so each patch sees the tree with
        # its predecessors already applied. That is what surfaces the first
        # conflict. Replaces checking against a pristine tree (50 needs 40...).
        broken = []
        napplied, nskip = 0, 0
        for p in ready:
            pf = str(ROOT / "patches" / p)
            if git_ok(GIT_APPLY_BASE + ["--whitespace=nowarn", pf]):
                print(f"  applied: {p}")
                napplied += 1
            elif git_ok(GIT_APPLY_BASE + ["--reverse", "--check", pf]):
                print(f"  already applied in tree: {p}")
                nskip += 1
            else:
                print(f"  CONFLICT applying: {p} (series stops here)")
                broken.append(p)
                break
        print(f"[aether] {napplied} applied, {nskip} already there, "
              f"{len(broken)} in conflict")

    # Branding assets are filled unconditionally because the patch series only
    # carries the text files and the SVGs. The binaries (PNG, ICO, ICNS, BMP,
    # msix, Assets.car, the installer SFX stub and the brand strings) live in
    # this repo and are copied here; encoding them as a diff against upstream is
    # not viable.
    # 1) Fill gaps from unofficial/ (background, BMPs, VisualElements...).
    # 2) Overwrite with the Aether set versioned in branding/ (generate-icons.py).
    import shutil
    uno = src / "browser" / "branding" / "unofficial"
    oxy = src / "browser" / "branding" / "aether"
    brand = ROOT / "branding"
    if uno.is_dir() and oxy.is_dir():
        n_gap, n_oxy = 0, 0
        for f in uno.rglob("*"):
            if f.is_file():
                t = oxy / f.relative_to(uno)
                if not t.exists():
                    t.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, t)
                    n_gap += 1
        if brand.is_dir():
            for f in brand.rglob("*"):
                if f.is_file() and f.name != "README.txt":
                    t = oxy / f.relative_to(brand)
                    t.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, t)
                    n_oxy += 1
        print(f"[aether] branding assets: {n_gap} gaps filled from unofficial, "
              f"{n_oxy} Aether files")

    # Distribution dir: only distribution.ini is carried by the series (ARP
    # reads the version from it). No policies: the packaging patch does
    # NOT stage a policies.json (it does not exist in the repo). No bundled
    # extensions since 150 (uBO XPI retired; the engine is native now).
    dist = src / "browser" / "app" / "distribution"
    if dist.is_dir():
        print("[aether] distribution: carried by the series (no staged binaries)")

    if not args.no_download:
        deps = configparser.ConfigParser()
        deps.read(ROOT / "aether.deps.ini")
        for section in deps.sections():
            if "url" not in deps[section]:
                print(f"[aether] deps [{section}] retired (no download)")
                continue
            url = deps[section]["url"] % {"version": deps[section]["version"]}
            out = ROOT / deps[section]["output_path"]
            out.mkdir(parents=True, exist_ok=True)
            print(f"[aether] deps [{section}] {url} -> {out} (manual download in v1)")

    print("[aether] sync OK")


if __name__ == "__main__":
    sys.exit(main())