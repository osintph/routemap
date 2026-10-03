"""
Pages for the pre-release download site: the root index (every version, the GPG
fingerprint, install notes) and one page per version (files, sizes, notes).

    python packaging/download_index.py version DIR VERSION NOTES.md > DIR/index.html
    python packaging/download_index.py root VERSIONS_FILE FINGERPRINT > index.html

Static HTML, no scripts, no external resources: the site sits behind HTTP basic
auth and serves files, nothing else.
"""
from __future__ import annotations

import html
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from routemap.__about__ import DISPLAY_NAME  # noqa: E402

STYLE = """
body{font:15px/1.55 -apple-system,"Segoe UI",system-ui,sans-serif;max-width:760px;margin:0 auto;
padding:24px 16px;color:#1e2d3d;background:#f6f8fa}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 8px}
table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid #d3dbe2}
code{font:13px ui-monospace,Menlo,Consolas,monospace;background:#e9eef2;padding:1px 4px;border-radius:3px}
.muted{color:#5d6b79}a{color:#0f6f66}
@media (prefers-color-scheme:dark){body{background:#0e151d;color:#e2e9f0}td,th{border-color:#2a3643}
code{background:#16202b}.muted{color:#96a4b2}a{color:#3cc3b4}}
"""


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<meta name='robots' content='noindex,nofollow'><title>{html.escape(title)}</title>"
            f"<style>{STYLE}</style></head><body>{body}</body></html>\n")


def _markdown(md: str) -> str:
    """Just enough Markdown for our own release notes: headings, lists, bold, code, links."""
    out, in_list = [], False
    for line in md.splitlines():
        text = html.escape(line)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"<a href='\2'>\1</a>", text)
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{text[2:]}</li>")
            continue
        if in_list and not line.startswith("  "):
            out.append("</ul>")
            in_list = False
        if line.startswith("### "):
            out.append(f"<h3>{text[4:]}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{text[3:]}</h2>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.startswith("  ") and in_list:
            out[-1] = out[-1][:-5] + " " + text.strip() + "</li>"
        elif line.strip():
            out.append(f"<p>{text}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def version_page(folder: str, version: str, notes_path: str) -> str:
    rows = []
    for f in sorted(pathlib.Path(folder).iterdir()):
        if f.name in ("index.html",) or f.is_dir():
            continue
        size = f.stat().st_size
        shown = f"{size / 1e6:.1f} MB" if size > 1e6 else f"{size} B"
        rows.append(f"<tr><td><a href='{html.escape(f.name)}'>{html.escape(f.name)}</a></td>"
                    f"<td>{shown}</td></tr>")
    notes = _markdown(pathlib.Path(notes_path).read_text(encoding="utf-8"))
    body = (f"<p class='muted'><a href='../'>All versions</a></p><h1>{DISPLAY_NAME} {html.escape(version)}</h1>"
            f"<table><tr><th>File</th><th>Size</th></tr>{''.join(rows)}</table>{notes}")
    return _page(f"{DISPLAY_NAME} {version}", body)


def root_page(versions_file: str, fingerprint: str) -> str:
    versions = [v.strip().strip("/") for v in pathlib.Path(versions_file).read_text().splitlines()
                if re.fullmatch(r"v?\d+\.\d+\.\d+[\w.-]*/?", v.strip())]
    versions.sort(key=lambda v: [int(x) if x.isdigit() else x for x in re.split(r"[.\-]", v.lstrip("v"))],
                  reverse=True)
    items = "".join(f"<tr><td><a href='{html.escape(v)}/'>{html.escape(v)}</a></td>"
                    f"<td>{'latest' if i == 0 else ''}</td></tr>" for i, v in enumerate(versions))
    body = (f"<h1>{DISPLAY_NAME} beta downloads</h1>"
            "<p class='muted'>For invited testers. Please do not share your login.</p>"
            f"<table><tr><th>Version</th><th></th></tr>{items}</table>"
            "<h2>Verify your download</h2>"
            "<p>Each version has <code>SHA256SUMS</code> and its signature <code>SHA256SUMS.asc</code>, "
            "made with this GPG release key:</p>"
            f"<p><code>{html.escape(fingerprint)}</code></p>"
            "<p><code>gpg --verify SHA256SUMS.asc SHA256SUMS</code>, then "
            "<code>sha256sum -c SHA256SUMS --ignore-missing</code> (Linux) or "
            "<code>shasum -a 256 -c SHA256SUMS --ignore-missing</code> (macOS), or "
            "<code>Get-FileHash</code> in PowerShell.</p>"
            "<h2>First run of an unsigned beta</h2>"
            "<p><b>Windows:</b> extract the zip and run <code>routemap.exe</code> in the "
            "<code>Route Map</code> folder; if SmartScreen warns, More info, then Run anyway. "
            "<b>macOS:</b> right-click Route Map in Applications, Open, Open; or "
            "<code>xattr -d com.apple.quarantine \"/Applications/Route Map.app\"</code>. "
            "<b>Linux:</b> <code>chmod +x</code> the AppImage.</p>")
    return _page(f"{DISPLAY_NAME} beta downloads", body)


def main(argv: list[str]) -> int:
    if argv[0] == "version":
        sys.stdout.write(version_page(argv[1], argv[2], argv[3]))
    elif argv[0] == "root":
        sys.stdout.write(root_page(argv[1], argv[2]))
    else:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
