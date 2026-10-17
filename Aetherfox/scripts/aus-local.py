"""Aether local AUS with buildID: avoids the endless re-offer.

`mach update serve` always advertises a fake future buildID, so the browser
offers the same update on every start. This server compares the BUILD_ID the
client sends (the AppUpdateURL policy has to include %VERSION%/%BUILD_ID%)
against the MAR's BuildID (the .buildid sidecar written by make-mar-local.py):
  - client < MAR   -> offer the update (complete patch)
  - client >= MAR  -> empty <updates></updates> ("already up to date")

Usage:
  python scripts/aus-local.py --dir C:\\aether-mar
      --mar aether-156.0.1.complete.mar --port 8000
"""
import argparse
import http.server
import os
import re
import socketserver
from functools import partial

UPDATE_RE = re.compile(r"/update(?:/([^/]+)/([^/]+)(?:/([^/]+))?)?/update\.xml")


class Handler(http.server.SimpleHTTPRequestHandler):
    mar_file = ""
    mar_buildid = ""
    app_version = "156.0"

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/update.xml":
            # Client using the old static URL (no %BUILD_ID%): there is
            # nothing to compare, so answer empty rather than re-offer in a
            # loop. Update its policies.json to the URL with placeholders.
            body = b"<updates></updates>"
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            print("[aus] {} -> up to date (static URL, update the policy)".format(
                self.path), flush=True)
            return
        m = UPDATE_RE.search(path)
        if m and path.endswith("update.xml"):
            ver, buildid, channel = m.group(1), m.group(2), m.group(3)
            offer = True
            if buildid and self.mar_buildid and buildid >= self.mar_buildid:
                offer = False
            if offer:
                size = os.path.getsize(
                    os.path.join(self.directory, self.mar_file))
                body = (
                    '<updates><update type="major" displayVersion="{v}" '
                    'appVersion="{v}" platformVersion="{v}" '
                    'buildID="{b}"><patch type="complete" '
                    'URL="http://127.0.0.1:8000/{m}" size="{s}" />'
                    "</update></updates>"
                ).format(v=self.app_version or "156.0",
                         b=self.mar_buildid or "2000.0a1",
                         m=self.mar_file, s=size)
            else:
                body = "<updates></updates>"
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            print("[aus] {} -> {}".format(
                self.path, "OFFER" if offer else "up to date"), flush=True)
            return
        return super().do_GET()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--mar", required=True)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--version", default=None,
                    help="displayVersion offered (default: derived from --mar)")
    args = ap.parse_args()
    if not args.version:
        m = re.match(r"aether-([\d.]+)\.complete\.mar$", args.mar)
        args.version = m.group(1) if m else "156.0"

    sidecar = os.path.join(args.dir, args.mar + ".buildid")
    buildid = ""
    if os.path.isfile(sidecar):
        buildid = open(sidecar, encoding="utf-8").read().strip()
    print("[aus] mar={} buildid={}".format(args.mar, buildid), flush=True)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(
            ("127.0.0.1", args.port),
            partial(Handler, directory=args.dir)) as httpd:
        Handler.mar_file = args.mar
        Handler.mar_buildid = buildid
        Handler.app_version = args.version
        print("[aus] serving on 127.0.0.1:{}".format(args.port), flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()