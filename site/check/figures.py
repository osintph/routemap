"""Check that no image renders outside its figure and nothing overlaps it.

    python site/check/figures.py <built site dir> [--widths 390,1280,...] [--schemes light,dark]

Serves the built site locally, loads every page in Chrome inside an iframe of
each width (an iframe, because headless Chrome will not make a window narrower
than 500 px), and measures in the page: each <img> in a figure must sit inside
the figure's box, and the figure's caption and the element after the figure
must start below the image. Prints the problems and exits 1 if there are any.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import pathlib
import shutil
import subprocess
import sys
import threading

WIDTHS = (390, 1280, 1366, 1440, 1536, 1920)
MEASURE = r"""<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" style="border:0;width:%(w)dpx;height:2000px" src="%(page)s"></iframe>
<pre id="result"></pre>
<script>
const frame = document.getElementById("f");
frame.addEventListener("load", () => setTimeout(() => {
  const doc = frame.contentDocument, out = [];
  // What site.js does when a visitor picks a theme, whatever the system's setting.
  const dark = %(dark)s;
  doc.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  doc.querySelectorAll("picture source[data-scheme]").forEach(s => s.media = dark ? "all" : "not all");
  // Let lazy images load and layout settle at this width.
  doc.querySelectorAll("img[loading=lazy]").forEach(i => i.loading = "eager");
  setTimeout(() => {
    const r = e => e.getBoundingClientRect();
    doc.querySelectorAll("img").forEach(img => {
      const fig = img.closest("figure") || img.closest("picture") || img.parentElement;
      if (!fig || !img.complete || img.naturalWidth === 0) return;
      const a = r(img), b = r(fig), name = (img.currentSrc || img.src).split("/").pop().split("?")[0];
      // A crop may scroll sideways inside its own box; vertical overflow is never fine.
      if (a.bottom > b.bottom + 1 || a.top < b.top - 1) out.push(`${name}: outside its figure (img ${Math.round(a.top)}..${Math.round(a.bottom)}, figure ${Math.round(b.top)}..${Math.round(b.bottom)})`);
      const cap = fig.querySelector("figcaption");
      if (cap && r(cap).top < a.bottom - 1) out.push(`${name}: caption overlaps the image by ${Math.round(a.bottom - r(cap).top)} px`);
      const next = (fig.tagName === "FIGURE" ? fig : fig.closest("figure") || fig).nextElementSibling;
      if (next && r(next).height > 0) {
        const n = r(next), sideBySide = n.left >= a.right - 1 || n.right <= a.left + 1;
        if (!sideBySide && n.top < a.bottom - 1) out.push(`${name}: the ${next.tagName.toLowerCase()}${next.className ? "." + next.className.split(" ")[0] : ""} after it overlaps the image by ${Math.round(a.bottom - n.top)} px`);
      }
    });
    document.getElementById("result").textContent = JSON.stringify(out);
  }, 1500);
}, 300));
</script>"""


def find_chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    for path in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if pathlib.Path(path).exists():
            return path
    return None


def check(site: pathlib.Path, widths=WIDTHS, schemes=("light", "dark"), chrome: str | None = None) -> list[str]:
    chrome = chrome or find_chrome()
    if not chrome:
        raise RuntimeError("Chrome not found")
    pages = sorted("/" if p.parent == site else "/" + p.parent.relative_to(site).as_posix() + "/"
                   for p in site.rglob("index.html") if "check" not in p.parts)
    # Pages with figures (every page has the logo <img>, which is not one).
    pages = [p for p in pages if "<figure" in (site / p.lstrip("/") / "index.html").read_text(encoding="utf-8")]
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    problems = []
    if True:
        probe_dir = site / "__check"
        probe_dir.mkdir(exist_ok=True)
        try:
            for page in pages:
                for width in widths:
                    for scheme in schemes:
                        name = f"{abs(hash((page, width, scheme)))}.html"
                        (probe_dir / name).write_text(MEASURE % {"w": width, "page": page,
                                                               "dark": "true" if scheme == "dark" else "false"},
                                                      encoding="utf-8")
                        dom = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--window-size=2000,2200",
                                              "--virtual-time-budget=6000", "--dump-dom",
                                              f"http://127.0.0.1:{port}/__check/{name}"],
                                             capture_output=True, text=True, timeout=120).stdout
                        start = dom.find('<pre id="result">')
                        raw = dom[start + 17:dom.find("</pre>", start)] if start >= 0 else ""
                        found = json.loads(raw.replace("&quot;", '"').replace("&amp;", "&")) if raw.strip() else ["no result"]
                        problems += [f"{page} at {width} px, {scheme}: {p}" for p in found]
        finally:
            shutil.rmtree(probe_dir, ignore_errors=True)
            server.shutdown()
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site")
    parser.add_argument("--widths", default=",".join(map(str, WIDTHS)))
    parser.add_argument("--schemes", default="light,dark")
    args = parser.parse_args(argv)
    problems = check(pathlib.Path(args.site), [int(w) for w in args.widths.split(",")], args.schemes.split(","))
    print("\n".join(problems) or "no figure overflows its box")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
