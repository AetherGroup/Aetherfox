"""Aether crash-tracker: watches the browser and hunts errors from our removals.

Two modes:
- session (default): launches aether/firefox with a temporary profile, captures
  stderr and prints the report on exit.
- live (--live): launches it in the foreground and shows every error IN REAL
  TIME while you use the browser (Ctrl+C to stop and see the summary).
- attach (--attach-port): connects over CDP to an ALREADY RUNNING browser
  (started with --remote-debugging-port) and shows its exceptions live.

Captures stderr (chrome JS errors with file:line:message), optionally CDP for
full stacks (who calls whom), watches minidumps and cross-references every
error against the knowledge base of Glean categories removed by the patches.

Stdlib only. It does not touch the tree or the user profile.

Usage:
  python scripts/crash-tracker.py --binary <aether.exe> [--url ...]
      [--time 60] [--cdp] [--headless] [--out reporte.json]
  python scripts/crash-tracker.py --binary <aether.exe> --live [--keep]
  python scripts/crash-tracker.py --attach-port 9222 [--time 0]
  python scripts/crash-tracker.py --self-test
"""
import argparse
import base64
import glob
import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH_DIR = ROOT / "patches" / "core"

# ---------------------------------------------------------------------------
# Knowledge base: Glean categories removed by the patches.
# ---------------------------------------------------------------------------

JS_CAT_RE = re.compile(r"^[a-z][\w.]*:$")
JS_METRIC_RE = re.compile(r"^  ([a-z][\w]*):$")


def yaml_cat_to_js(cat):
    """browser.backup -> browserBackup ; extensions_button -> extensionsButton."""
    parts = re.split(r"[._]", cat)
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def build_kb():
    """Returns {js_category: {patch, yaml, metrics[]}} + {file: [patches]}.

    Reads the patches (the base repo is not needed): the categories come from
    the removed content ('-' lines of deleted metrics.yaml files).
    """
    kb = {}
    touched = {}
    for pn in sorted(glob.glob(str(PATCH_DIR / "*.patch"))):
        name = os.path.basename(pn)
        lines = open(pn, encoding="utf-8", errors="replace").read().split(
            "\n")
        cur_deleted_yaml = None
        for i, line in enumerate(lines):
            m = re.match(r"^diff --git a/(\S+) b/\S+$", line)
            if m:
                path = m.group(1)
                if not path.startswith("tests/") and "/test" not in path:
                    touched.setdefault(path, []).append(name)
                # Deleted file? 'deleted file mode' comes in the lines after
                # 'diff --git'; if it is a metrics/pings yaml, start
                # capturing categories.
                cur_deleted_yaml = None
                window = "\n".join(lines[i:i + 4])
                if "deleted file mode" in window and (
                        path.endswith("metrics.yaml")
                        or path.endswith("pings.yaml")):
                    cur_deleted_yaml = path
                    continue
            elif cur_deleted_yaml and line.startswith("-") \
                    and not line.startswith("---"):
                body = line[1:]
                mc = JS_CAT_RE.match(body)
                if mc:
                    js = yaml_cat_to_js(mc.group(0)[:-1])
                    kb.setdefault(js, {"patch": name,
                                       "yaml": cur_deleted_yaml,
                                       "metrics": []})
                else:
                    mm = JS_METRIC_RE.match(body)
                    if mm and kb:
                        last = list(kb)[-1]
                        if kb[last]["yaml"] == cur_deleted_yaml:
                            kb[last]["metrics"].append(mm.group(1))
    return kb, touched


# ---------------------------------------------------------------------------
# Parser for the browser stderr.
# ---------------------------------------------------------------------------

JS_ERROR_RE = re.compile(
    r"JavaScript error:\s*(?P<file>\S+?),\s*line\s*(?P<line>\d+)"
    r"(?:,\s*col(?:umn)?\s*(?P<col>\d+))?:\s*(?P<msg>.*)")
CONSOLE_RE = re.compile(
    r"console\.(?P<level>error|warn|info|log):\s*(?P<msg>.*)")
FATAL_RES = [
    re.compile(r"###!!!\s*(?P<msg>ABORT.*)"),
    re.compile(r"Assertion failure:\s*(?P<msg>.*)"),
    re.compile(r"Crash Annotation.*"),
    re.compile(r"Redirecting call to abort\(\)"),
]
# Shutdown noise: the IPC channel breaks on close (also when we terminate the
# process ourselves). Only fatal if the exit is abnormal.
SHUTDOWN_NOISE_RES = [
    re.compile(r"Exiting due to channel error\.?"),
    re.compile(r"console\.log: WebRender.*shutDown", re.I),
]
GLEAN_RE = re.compile(r"Glean\.([A-Za-z][\w]*)")


def parse_stderr(text):
    """Returns (errors[{file,line,col,msg,count}], fatals[str])."""
    sp = StreamParser()
    for raw in text.split("\n"):
        sp.feed(raw)
    return sp.result()


class StreamParser:
    """Incremental line-by-line parser for live mode.

    on_new(error_dict) is called for each NEW group (file,line,msg);
    on_fatal(str) for each fatal line. Repeats only bump the count.
    """

    def __init__(self, on_new=None, on_fatal=None):
        self.errors = {}
        self.fatales = []
        self.shutdown_noise = []
        self.pending = None
        self.on_new = on_new
        self.on_fatal = on_fatal

    def feed(self, raw):
        line = raw.rstrip("\r").rstrip("\n")
        m = JS_ERROR_RE.search(line)
        if m:
            key = (m.group("file"), int(m.group("line")),
                   (m.group("msg") or "").strip()[:300])
            e = self.errors.get(key)
            if e is None:
                e = self.errors[key] = {
                    "file": key[0], "line": key[1],
                    "col": m.group("col"), "msg": key[2], "count": 0,
                    "context": []}
                if self.on_new:
                    self.on_new(e)
            e["count"] += 1
            self.pending = e
            return
        m = CONSOLE_RE.search(line)
        if m and m.group("level") == "error":
            key = ("console", 0, m.group("msg").strip()[:300])
            e = self.errors.get(key)
            if e is None:
                e = self.errors[key] = {
                    "file": "console", "line": 0, "col": None,
                    "msg": key[2], "count": 0, "context": []}
                if self.on_new:
                    self.on_new(e)
            e["count"] += 1
            self.pending = e
            return
        for frx in FATAL_RES:
            fm = frx.search(line)
            if fm:
                try:
                    msg = fm.group("msg") or line.strip()
                except IndexError:
                    msg = line.strip()
                self.fatales.append(msg)
                if self.on_fatal:
                    self.on_fatal(msg)
                self.pending = None
                return
        for nrx in SHUTDOWN_NOISE_RES:
            if nrx.search(line):
                self.shutdown_noise.append(line.strip()[:200])
                self.pending = None
                return
        if self.pending is not None and line[:1] in (" ", "\t"):
            if len(self.pending["context"]) < 8:
                self.pending["context"].append(line.strip()[:200])
        elif line.strip():
            self.pending = None

    def result(self):
        return list(self.errors.values()), self.fatales

    def demote_shutdown_noise(self):
        """If the exit was clean, the shutdown noise was not fatal."""
        n = len(self.shutdown_noise)
        self.shutdown_noise = []
        return n


# ---------------------------------------------------------------------------
# Minimal WebSocket client (stdlib) for CDP.
# ---------------------------------------------------------------------------

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class MiniWS:
    def __init__(self, host, port, path, use_tls=False):
        s = socket.create_connection((host, port), timeout=10)
        if use_tls:
            s = ssl.create_default_context().wrap_socket(
                s, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
               f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\n"
               f"Sec-WebSocket-Version: 13\r\n\r\n")
        s.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = s.recv(4096)
            if not chunk:
                raise ConnectionError("handshake WS fallido")
            resp += chunk
        accept = hashlib.sha1((key + WS_GUID).encode()).digest()
        if base64.b64encode(accept).decode() not in \
                resp.decode("latin1", "replace"):
            raise ConnectionError("handshake WS: accept invalido")
        self.s = s
        self.lock = threading.Lock()

    def send(self, obj):
        data = json.dumps(obj).encode()
        hdr = bytes([0x81])
        n = len(data)
        mask = os.urandom(4)
        if n < 126:
            hdr += struct.pack("!B", 0x80 | n)
        elif n < 65536:
            hdr += struct.pack("!BBH", 0x80 | 126, n)
        else:
            hdr += struct.pack("!BQ", 0x80 | 127, n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        with self.lock:
            self.s.sendall(hdr + mask + masked)

    def _recvn(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("WS cerrado")
            buf += chunk
        return buf

    def recv(self, timeout=None):
        self.s.settimeout(timeout)
        try:
            b1, b2 = self._recvn(2)
        except (socket.timeout, TimeoutError):
            return None
        opcode = b1 & 0x0F
        if opcode == 0x8:
            raise ConnectionError("WS closed by the peer")
        ln = b2 & 0x7F
        if ln == 126:
            ln = struct.unpack("!H", self._recvn(2))[0]
        elif ln == 127:
            ln = struct.unpack("!Q", self._recvn(8))[0]
        if b2 & 0x80:
            mask = self._recvn(4)
        else:
            mask = None
        data = self._recvn(ln)
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if opcode == 0x1:
            return json.loads(data.decode("utf-8", "replace"))
        return None

    def close(self):
        try:
            with self.lock:
                self.s.sendall(bytes([0x88, 0x00]))
        except OSError:
            pass
        try:
            self.s.close()
        except OSError:
            pass


def cdp_listen(port, seconds, out_events, on_event=None):
    """Connects to the browser target and collects Runtime.exceptionThrown.

    seconds=0 means forever (until Ctrl+C / shutdown). With on_event,
    every exception is delivered live as well as accumulated.
    """
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version",
                timeout=10) as r:
            info = json.loads(r.read().decode())
    except Exception as ex:
        return f"no CDP (/json/version): {ex}"
    ws_url = info.get("webSocketDebuggerUrl", "")
    m = re.match(r"(wss?)://127\.0\.0\.1(?::(\d+))?(/.*)", ws_url)
    if not m:
        # Firefox exposes the targets at /json/list; use the first one.
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/list",
                    timeout=10) as r:
                targets = json.loads(r.read().decode())
            ws_url = (targets or [{}])[0].get("webSocketDebuggerUrl", "")
            m = re.match(r"(wss?)://127\.0\.0\.1(?::(\d+))?(/.*)", ws_url)
        except Exception as ex:
            return f"no CDP (/json/list): {ex}"
    if not m:
        return "no CDP: no webSocketDebuggerUrl"
    try:
        ws = MiniWS("127.0.0.1", int(m.group(2) or port), m.group(3),
                    use_tls=(m.group(1) == "wss"))
    except Exception as ex:
        return f"no CDP (WS): {ex}"
    seq = [0]

    def send(method, params=None):
        seq[0] += 1
        ws.send({"id": seq[0], "method": method,
                 "params": params or {}})

    try:
        send("Runtime.enable")
        send("Log.enable")
        end = time.time() + seconds if seconds > 0 else None
        while end is None or time.time() < end:
            msg = ws.recv(timeout=2)
            if not msg:
                continue
            if msg.get("method") == "Runtime.exceptionThrown":
                params = msg.get("params", {})
                out_events.append(params)
                if on_event:
                    on_event(params)
            elif msg.get("method") == "Log.entryAdded":
                entry = msg.get("params", {}).get("entry", {})
                if entry.get("level") in ("error",):
                    wrapped = {"logEntry": entry}
                    out_events.append(wrapped)
                    if on_event:
                        on_event(wrapped)
    except ConnectionError:
        pass
    finally:
        ws.close()
    return None


# ---------------------------------------------------------------------------
# Lanzador + informe.
# ---------------------------------------------------------------------------

def wait_cdp(port, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version",
                    timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def snapshot_dumps(profile):
    out = []
    for pat in ("minidumps/*.dmp", "*.dmp"):
        out.extend(str(p) for p in Path(profile).glob(pat))
    return set(out)


UPDATE_WATCH_PATS = ("updates/0/update.status", "updates/0/update.version",
                     "updates/0/active-update.xml", "updates.xml",
                     "update.status", "last-update.log",
                     "backup-update.log")


class UpdateWatcher:
    """Watches the update flow: update.status, updates.xml and the updater
    logs in the installation directory and in the profile.

    poll() -> [(path, evento, detalle)]: evento en {nuevo, cambio}.
    The detail is the last lines (status) or the tail of the log.
    """

    def __init__(self, installdir=None, profile=None):
        self.roots = []
        if installdir:
            self.roots.append(Path(installdir))
        if profile:
            self.roots.append(Path(profile))
        self.state = {}
        self.snapshot()

    def _files(self):
        for root in self.roots:
            if not root.is_dir():
                continue
            for pat in UPDATE_WATCH_PATS:
                for p in root.glob("**/" + pat):
                    yield p
            # the profile's updates.xml is usually at the root
            for name in ("updates.xml",):
                p = root / name
                if p.is_file():
                    yield p

    def snapshot(self):
        for p in self._files():
            try:
                st = p.stat()
                self.state[str(p)] = (st.st_mtime, st.st_size)
            except OSError:
                pass

    def _tail(self, p, n=6):
        try:
            lines = p.read_text(encoding="utf-8",
                                errors="replace").split("\n")
            return "\n".join(l.strip()[:160] for l in lines[-n:]
                             if l.strip())
        except OSError:
            return ""

    def poll(self):
        events = []
        seen = set()
        for p in self._files():
            sp = str(p)
            seen.add(sp)
            try:
                st = p.stat()
                cur = (st.st_mtime, st.st_size)
            except OSError:
                continue
            old = self.state.get(sp)
            if old is None:
                self.state[sp] = cur
                events.append((sp, "nuevo", self._tail(p)))
            elif old != cur:
                self.state[sp] = cur
                events.append((sp, "cambio", self._tail(p)))
        return events


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--binary", required=False,
                    help="aether.exe / firefox.exe a vigilar")
    ap.add_argument("--profile", default=None,
                    help="profile (default: a clean temporary one)")
    ap.add_argument("--url", action="append", default=[],
                    help="URL a abrir (repetible)")
    ap.add_argument("--time", type=int, default=60,
                    help="seconds to listen (default 60; 0 = forever)")
    ap.add_argument("--cdp", action="store_true",
                    help="connect over CDP for full stacks")
    ap.add_argument("--cdp-port", type=int, default=9222)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--live", action="store_true",
                    help="real time: show every error as it happens "
                    "while you use the browser (Ctrl+C = summary and exit)")
    ap.add_argument("--keep", action="store_true",
                    help="with --live/--time: when finished, do not close the "
                    "navegador lanzado")
    ap.add_argument("--attach-port", type=int, default=None, metavar="PORT",
                    help="launch nothing: connect over CDP to a browser "
                    "ALREADY RUNNING with --remote-debugging-port=PORT and listen "
                    "sus excepciones en vivo")
    ap.add_argument("--watch-updates", default=None, metavar="INSTALLDIR",
                    help="watch the update flow live (update.status, "
                    "updates.xml, updater logs) in the "
                    "instalacion + perfil")
    ap.add_argument("--out", default=None, help="JSON report")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("extra_args", nargs="*", help="extra args for the browser")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()

    kb, touched = build_kb()
    print(f"[tracker] KB: {len(kb)} categories removed in "
          f"{len(set(v['patch'] for v in kb.values()))} patches")

    if a.attach_port:
        return run_attach(a, kb, touched)
    return run_launch(a, kb, touched)


def write_out(a, report):
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)


def exit_code(report, fatales, dumps, rc):
    # exit code != 0 if there were chrome JS errors, fatals or a crash.
    if report["summary"]["chrome_errors"] or fatales or dumps \
            or (rc not in (0, None)):
        return 1
    return 0


def run_attach(a, kb, touched):
    """Watch an ALREADY RUNNING browser live over CDP (exceptions only)."""
    print(f"[tracker] attaching to CDP on 127.0.0.1:{a.attach_port} "
          f"({'forever, Ctrl+C to exit' if not a.time else f'{a.time}s'})")
    cdp_events = []
    holder = {}

    def on_event(ev):
        if "exceptionDetails" in ev or "logEntry" in ev:
            print_cdp_item(cdp_item(ev))

    if not wait_cdp(a.attach_port, timeout=10):
        print("[tracker] no CDP response: was the browser started with "
              "--remote-debugging-port=PORT?", file=sys.stderr)
        return 2
    try:
        err = cdp_listen(a.attach_port, a.time, cdp_events,
                         on_event=on_event)
    except KeyboardInterrupt:
        err = None
        print("\n[tracker] interrupted by the user")
    if err:
        print(f"[tracker] {err}", file=sys.stderr)
    report = build_report([], [], cdp_events, kb, touched, [], None,
                          err)
    print_report(report)
    write_out(a, report)
    if a.out:
        print(f"[tracker] informe en {a.out}")
    return 0 if not err else 1


def run_launch(a, kb, touched):
    if not a.binary:
        print("missing --binary (or use --self-test / --attach-port)",
              file=sys.stderr)
        return 2
    if a.live:
        return run_live(a, kb, touched)

    profile = a.profile or tempfile.mkdtemp(prefix="ox-crashwatch-")
    tmp_profile = a.profile is None
    before_dumps = snapshot_dumps(profile)

    cmd = [a.binary, "-profile", profile, "-no-remote"]
    if a.headless:
        cmd.append("--headless")
    if a.cdp:
        cmd += ["--remote-debugging-port", str(a.cdp_port)]
    cmd += a.url + a.extra_args
    print("[tracker] lanzando:", " ".join(cmd))

    cdp_events = []
    cdp_err = None
    cdp_thread = None
    holder = {}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True, errors="replace")
    try:
        if a.cdp:
            if wait_cdp(a.cdp_port, timeout=min(30, a.time)):
                # real thread, stores the error in holder if there is one
                cdp_thread = threading.Thread(
                    target=lambda: holder.update(
                        err=cdp_listen(a.cdp_port, a.time, cdp_events)))
                cdp_thread.daemon = True
                cdp_thread.start()
            else:
                cdp_err = "CDP port not responding"
        try:
            out, _ = proc.communicate(timeout=a.time)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                out, _ = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, _ = proc.communicate()
    finally:
        if cdp_thread is not None:
            cdp_thread.join(timeout=10)
    rc = proc.returncode
    if cdp_thread is not None:
        cdp_err = holder.get("err")

    errors, fatales = parse_stderr(out or "")
    # parse_stderr does not expose the noise: re-evaluating is cheap and
    # only tells us whether there were shutdown lines with a clean exit.
    noise = 0
    if rc == 0:
        for raw in (out or "").split("\n"):
            if any(nrx.search(raw) for nrx in SHUTDOWN_NOISE_RES):
                noise += 1
    after_dumps = snapshot_dumps(profile)
    new_dumps = sorted(after_dumps - before_dumps)
    if tmp_profile:
        shutil.rmtree(profile, ignore_errors=True)

    report = build_report(errors, fatales, cdp_events, kb, touched,
                          new_dumps, rc, cdp_err)
    report["summary"]["ruido_apagado"] = noise
    print_report(report)
    write_out(a, report)
    if a.out:
        print(f"[tracker] informe en {a.out}")
    return exit_code(report, fatales, new_dumps, rc)


def run_live(a, kb, touched):
    """Launches the browser and shows every error IN REAL TIME.

    Ctrl+C or the end of --time: a final summary. With --keep the browser
    is not closed at the end; without --keep it is.
    """
    profile = a.profile or tempfile.mkdtemp(prefix="ox-crashwatch-")
    tmp_profile = a.profile is None
    before_dumps = snapshot_dumps(profile)

    cmd = [a.binary, "-profile", profile, "-no-remote"]
    if a.headless:
        cmd.append("--headless")
    if a.cdp:
        cmd += ["--remote-debugging-port", str(a.cdp_port)]
    cmd += a.url + a.extra_args
    print("[tracker] live:", " ".join(cmd))
    print("[tracker] Ctrl+C = summary and exit"
          + (" (the browser is still open)" if a.keep else ""))

    state = {"seen": 0}
    cdp_events = []
    holder = {}
    cdp_thread = None
    ctx = {}

    def save():
        errs, _ = sp.result()
        report = build_report(errs, sp.fatales, cdp_events, kb,
                              touched, sorted(snapshot_dumps(profile)
                                              - before_dumps),
                              ctx["proc"].returncode, holder.get("err"))
        write_out(a, report)

    def on_new(e):
        item = enrich(e, kb, touched)
        item["count"] = 1
        state["seen"] += 1
        print(f"[live #{state['seen']}] ", end="", flush=True)
        print_error_item(item)
        save()

    def on_fatal(msg):
        print(f"  [fatal] {msg[:200]}", flush=True)

    def on_cdp(ev):
        if "exceptionDetails" in ev or "logEntry" in ev:
            print_cdp_item(cdp_item(ev))

    sp = StreamParser(on_new=on_new, on_fatal=on_fatal)
    uw = UpdateWatcher(a.watch_updates, profile) \
        if a.watch_updates else None
    last_poll = 0.0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True, errors="replace",
                            bufsize=1)
    ctx["proc"] = proc
    start = time.time()
    try:
        if a.cdp:
            if wait_cdp(a.cdp_port, timeout=min(30, a.time or 30)):
                cdp_thread = threading.Thread(
                    target=lambda: holder.update(
                        err=cdp_listen(a.cdp_port, a.time, cdp_events,
                                       on_event=on_cdp)))
                cdp_thread.daemon = True
                cdp_thread.start()
            else:
                holder["err"] = "CDP port not responding"
        while True:
            if proc.poll() is not None:
                rest = proc.stdout.read()
                if rest:
                    for ln in rest.split("\n"):
                        sp.feed(ln)
                print(f"[tracker] the browser exited "
                      f"(exit={proc.returncode})")
                break
            if a.time and time.time() - start > a.time:
                print(f"[tracker] end of --time {a.time}s")
                break
            if uw is not None and time.time() - last_poll > 2:
                last_poll = time.time()
                for path, ev, detail in uw.poll():
                    print(f"[updates] {path}: {ev}", flush=True)
                    for dl in detail.split("\n")[:6]:
                        if dl.strip():
                            print(f"      | {dl.strip()[:160]}",
                                  flush=True)
            line = proc.stdout.readline()
            if line:
                sp.feed(line)
            else:
                time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n[tracker] interrupted by the user")
    finally:
        if cdp_thread is not None:
            cdp_thread.join(timeout=10)
        if not a.keep and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    errors, fatales = sp.result()
    new_dumps = sorted(snapshot_dumps(profile) - before_dumps)
    if tmp_profile and not a.keep:
        shutil.rmtree(profile, ignore_errors=True)
    noise = 0
    if proc.returncode == 0:
        noise = sp.demote_shutdown_noise()
    report = build_report(errors, fatales, cdp_events, kb, touched,
                          new_dumps, proc.returncode, holder.get("err"))
    report["summary"]["ruido_apagado"] = noise
    if uw is not None:
        upd = {}
        for p in uw.state:
            upd[p] = uw._tail(Path(p))
        report["updates"] = upd
        for up, tail in upd.items():
            first = (tail.split("\n")[0] if tail else "")[:120]
            print(f"  [updates] {up}: {first}")
    print_report(report)
    write_out(a, report)
    if a.out:
        print(f"[tracker] informe en {a.out}")
    return exit_code(report, fatales, new_dumps, proc.returncode)


def enrich(e, kb, touched):
    cats = sorted(set(GLEAN_RE.findall(e["msg"])))
    kb_hits = [{"category": c, "patch": kb[c]["patch"],
                "yaml": kb[c]["yaml"]}
               for c in cats if c in kb]
    chrome = e["file"].startswith(
        ("resource:", "chrome:", "jar:", "moz-")) \
        or e["file"].endswith((".sys.mjs", ".js", ".mjs", ".xhtml"))
    return {
        "file": e["file"], "line": e["line"], "col": e["col"],
        "msg": e["msg"], "count": e["count"], "chrome": chrome,
        "glean_cats": cats, "kb": kb_hits,
        "tocado_por": touched.get(path_hint(e["file"]), []),
        "areas": area_hints(e["msg"] + " " + e["file"], touched),
        "context": e["context"],
    }


def cdp_item(ev):
    if "exceptionDetails" in ev:
        d = ev["exceptionDetails"]
        frames = [{"func": fr.get("functionName", "?"),
                   "file": fr.get("url", "?"),
                   "line": fr.get("lineNumber"),
                   "col": fr.get("columnNumber")}
                  for fr in d.get("stackTrace", {})
                  .get("callFrames", [])]
        return {"text": d.get("text", ""),
                "file": d.get("url", "?"),
                "line": d.get("lineNumber"),
                "frames": frames}
    en = ev["logEntry"]
    return {"text": en.get("text", ""),
            "file": (en.get("url") or "?"),
            "line": en.get("lineNumber"),
            "frames": []}


def build_report(errors, fatales, cdp_events, kb, touched, dumps, rc,
                 cdp_err):
    items = [enrich(e, kb, touched) for e in errors]
    stacks = []
    for ev in cdp_events:
        if isinstance(ev, str):
            continue
        if "exceptionDetails" in ev or "logEntry" in ev:
            stacks.append(cdp_item(ev))
    items.sort(key=lambda x: (-x["count"], x["file"]))
    return {
        "summary": {
            "chrome_errors": sum(1 for i in items if i["chrome"]),
            "total_error_hits": sum(i["count"] for i in items),
            "fatales": len(fatales),
            "cdp_exceptions": len(stacks),
            "minidumps": len(dumps),
            "exit_code": rc,
            "kb_categories": len(kb),
            "ruido_apagado": 0,
        },
        "errors": items,
        "fatales": fatales,
        "cdp": stacks,
        "minidumps": dumps,
        "cdp_error": cdp_err,
    }


def path_hint(chrome_url):
    """resource://gre/modules/Foo.sys.mjs -> toolkit/modules/Foo.sys.mjs
    (approximate; only used to suggest the patches involved)."""
    m = re.match(r"resource://(?:gre|app)/modules/(.+)", chrome_url)
    if m:
        return "toolkit/modules/" + m.group(1)
    m = re.match(r"chrome://browser/content/(.+)", chrome_url)
    if m:
        return "browser/base/content/" + m.group(1)
    return chrome_url


# Component named in the message -> files to look up in `touched`.
# For console errors with no file:line, this gives the area hint.
AREA_HINTS = [
    (re.compile(r"services\.settings|remote-settings|RemoteSettings",
                re.I),
     "remote-settings", ["services/settings", "toolkit/components/normandy",
                         "remote-settings"]),
    (re.compile(r"ASRouter|asrouter|newtab|newTab", re.I),
     "mensajeria/newtab", ["asrouter", "newtab"]),
    (re.compile(r"addons|XPIDatabase|Addons?Manager|extensions",
                re.I),
     "addons", ["mozapps/extensions", "extensions/"]),
    (re.compile(r"update|updater|aus|mar", re.I),
     "updates", ["mozapps/update", "update"]),
    (re.compile(r"Glean\.([A-Za-z][\w]*)"), "glean", []),
    (re.compile(r"sync|fxa|fxaccounts", re.I),
     "sync", ["services/sync", "fxaccounts"]),
    (re.compile(r"telemetry|Telemetry|Glean", re.I),
     "telemetria", []),
]


def area_hints(msg, touched):
    """[(label, [patches])] for the given message."""
    out = []
    for rx, label, keys in AREA_HINTS:
        m = rx.search(msg)
        if not m:
            continue
        if label == "glean":
            continue  # the KB already covers it
        patches = set()
        for path, plist in touched.items():
            if any(k in path for k in keys):
                patches.update(plist)
        out.append((label, sorted(patches)[:4]))
    return out


def print_error_item(e):
    flag = ""
    if e["kb"]:
        flag = "  <-- " + "; ".join(
            f"{h['category']} removed in {h['patch']}"
            for h in e["kb"])
    print(f"  {e['count']}x {e['file']}:{e['line']}: "
          f"{e['msg'][:160]}{flag}", flush=True)
    for fr in e["context"][:3]:
        print(f"      | {fr}", flush=True)
    for label, patches in e.get("areas", []):
        if patches:
            print(f"      ~ area {label}: touched by "
                  f"{', '.join(patches)}", flush=True)
        else:
            print(f"      ~ area {label} (no patches involved)",
                  flush=True)


def print_cdp_item(st):
    print(f"  [cdp] {st['file']}:{st['line']}: "
          f"{st['text'][:160]}", flush=True)
    for fr in st["frames"][:6]:
        print(f"      at {fr['func']} "
              f"({fr['file']}:{fr['line']})", flush=True)


def print_report(rep):
    s = rep["summary"]
    print(f"[tracker] errores chrome: {s['chrome_errors']} "
          f"({s['total_error_hits']} impactos) | fatales: {s['fatales']} | "
          f"CDP: {s['cdp_exceptions']} | minidumps: {s['minidumps']} | "
          f"exit: {s['exit_code']}", flush=True)
    if s.get("ruido_apagado"):
        print(f"[tracker] shutdown noise ignored "
              f"({s['ruido_apagado']} lines, clean exit)", flush=True)
    for e in rep["errors"][:20]:
        print_error_item(e)
    for st in rep["cdp"][:10]:
        print_cdp_item(st)
    for f in rep["fatales"][:10]:
        print(f"  [fatal] {f[:200]}")
    for d in rep["minidumps"]:
        print(f"  [dump] {d}")
    if rep["cdp_error"]:
        print(f"  [cdp] {rep['cdp_error']}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------

FAKE_STDERR = """\
[Parent 1234] JavaScript error: resource://gre/modules/BrowserTelemetryUtils.sys.mjs, line 42: TypeError: Glean.browserUiInteraction is undefined
[Parent 1234] JavaScript error: chrome://browser/content/browser.js, line 3847: TypeError: can't access property \"add\" of Glean.messagingSystem.lastWindowCloseTriggerBypassed is undefined
console.error: NS_ERROR_FAILURE when opening about:config
###!!! ABORT: file widget/windows/nsWindow.cpp, line 999
[Parent 1234] JavaScript error: resource://gre/modules/BrowserTelemetryUtils.sys.mjs, line 42: TypeError: Glean.browserUiInteraction is undefined
"""


def self_test():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"[{'OK' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    errors, fatales = parse_stderr(FAKE_STDERR)
    check("groups repeats", len(errors) == 3)
    first = [e for e in errors
             if "browserUiInteraction" in e["msg"]][0]
    check("file/line", first["file"].endswith(
        "BrowserTelemetryUtils.sys.mjs") and first["line"] == 42)
    check("count", first["count"] == 2)
    check("fatal", any("ABORT" in f for f in fatales))

    kb, touched = build_kb()
    check("KB not empty", len(kb) > 10)
    # The KB maps each removed Glean category to the patch that deleted its
    # yaml. The stack gets renumbered constantly (124- is long gone), so the
    # check is that the named patch exists and keeps the NN-* naming, never a
    # fixed number.
    ui_patch = kb.get("browserUiInteraction", {}).get("patch", "")
    check("KB browserUiInteraction",
          bool(ui_patch) and (PATCH_DIR / ui_patch).is_file()
          and re.match(r"^\d{2,3}-", ui_patch) is not None)
    check("KB trustpanel", "trustpanel" in kb)
    rep = build_report(errors, fatales, [], kb, touched, [], 0, None)
    hits = {}
    for e in rep["errors"]:
        for h in e["kb"]:
            hits[h["category"]] = h["patch"]
    # browserUiInteraction (its sidebar yaml is gone) and messagingSystem (the
    # asrouter yaml went with it) are both in the KB, and nothing else is.
    check("KB cross-reference",
          hits.get("browserUiInteraction") == ui_patch
          and "messagingSystem" in hits and len(hits) == 2)
    # a category the stack still ships is never blamed on a patch
    alive = dict(errors[0])
    alive.update({"file": "resource://gre/modules/StillAlive.sys.mjs",
                  "line": 7, "col": None,
                  "msg": "TypeError: Glean.someAliveCategory is undefined"})
    rep_alive = build_report([alive], [], [], kb, touched, [], 0, None)
    check("no false positive",
          all(not e["kb"] for e in rep_alive["errors"]))

    # shutdown noise: kept apart from fatals and degrades with exit 0
    sp2 = StreamParser()
    sp2.feed("Exiting due to channel error.")
    sp2.feed("Exiting due to channel error.")
    e2, f2 = sp2.result()
    check("noise separated", not e2 and not f2
          and len(sp2.shutdown_noise) == 2)
    check("demote", sp2.demote_shutdown_noise() == 2
          and not sp2.shutdown_noise)

    # area hint: a remote-settings console error points at the patches
    areas = area_hints("services.settings: Polling for changes failed",
                       touched)
    check("area hints", any(a[0] == "remote-settings" for a in areas))

    # WS codec: roundtrip of one masked frame
    import io

    class FakeSock:
        def __init__(self, data):
            self.buf = io.BytesIO(data)
            self.sent = b""

        def sendall(self, d):
            self.sent += d

        def recv(self, n):
            return self.buf.read(n)

        def settimeout(self, t):
            pass

        def close(self):
            pass

    ws = MiniWS.__new__(MiniWS)
    payload = json.dumps({"id": 1, "method": "Runtime.enable"}).encode()
    mask = b"\x01\x02\x03\x04"
    frame = bytes([0x81, 0x80 | len(payload)]) + mask + bytes(
        b ^ mask[i % 4] for i, b in enumerate(payload))
    ws.s = FakeSock(frame)
    ws.lock = threading.Lock()
    msg = ws.recv(timeout=5)
    check("WS roundtrip", msg == {"id": 1, "method": "Runtime.enable"})
    ws.s = FakeSock(b"")
    ws.send({"hello": 1})
    check("WS send masked", ws.s.sent[:1] == b"\x81")

    # CDP dispatch: exceptionThrown with a stack
    ev = {"exceptionDetails": {
        "text": "TypeError: Glean.foo is undefined",
        "url": "chrome://browser/content/browser.js",
        "lineNumber": 100, "columnNumber": 5,
        "stackTrace": {"callFrames": [
            {"functionName": "f", "url": "chrome://x/a.js",
             "lineNumber": 10, "columnNumber": 1},
            {"functionName": "g", "url": "chrome://x/b.js",
             "lineNumber": 20, "columnNumber": 2}]}}}
    rep2 = build_report([], [], [ev], kb, touched, [], 0, None)
    check("CDP stack",
          len(rep2["cdp"]) == 1 and len(rep2["cdp"][0]["frames"]) == 2)
    print("[tracker] self-test:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
