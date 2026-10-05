"""Open Graph previews (1200 x 630) for the pages people share, drawn in the
site's own type and colours with a slice of the app, rendered by Chrome.

    python site/og/make_og.py [--chrome PATH]

Writes site/assets/og/<name>.jpg. Rerun after changing CARDS or the fonts;
the images are committed, so a site build needs neither Chrome nor this script.
"""
from __future__ import annotations

import argparse
import html
import pathlib
import subprocess
import sys
import tempfile

SITE = pathlib.Path(__file__).resolve().parents[1]
FONTS = SITE / "assets" / "fonts"
SHOT = SITE / "assets" / "img" / "window-dark.jpg"
ICON = SITE / "assets" / "icon-192.png"

# name: (headline, line). The words are the page's own promise, in plain terms.
CARDS = {
    "home": ("See where your packets actually went.",
             "A traceroute on a world map, each router placed by its hostname and checked against the round-trip time. Free and open source."),
    "download": ("Download Route Map",
                 "Free and open source. Windows installer, macOS DMG, Linux .deb, .rpm and AppImage."),
    "docs": ("Route Map documentation",
             "Install it, run a first trace, read the map and the hop table, use the command line."),
}

TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: "Newsreader"; src: url("{fonts}/newsreader-var.woff2") format("woff2"); font-weight: 500 700; }}
@font-face {{ font-family: "Schibsted Grotesk"; src: url("{fonts}/schibsted-grotesk-var.woff2") format("woff2"); font-weight: 400 700; }}
html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; background: #0b1520; }}
.card {{ position: relative; width: 1200px; height: 630px; display: grid; grid-template-columns: 660px 1fr; }}
.text {{ padding: 64px 0 56px 72px; display: flex; flex-direction: column; }}
.mark {{ display: flex; align-items: center; gap: 14px; color: #e8edf2; font: 600 30px "Newsreader", Georgia, serif; }}
.mark img {{ width: 44px; height: 44px; }}
.rule {{ width: 72px; height: 4px; background: #f0a440; border-radius: 2px; margin: 38px 0 26px; }}
h1 {{ margin: 0; color: #e8edf2; font: 600 56px/1.08 "Newsreader", Georgia, serif; letter-spacing: -0.01em; text-wrap: balance; }}
p {{ margin: 26px 0 0; color: #c4cdd7; font: 400 23px/1.42 "Schibsted Grotesk", Arial, sans-serif; max-width: 32ch; }}
.url {{ margin-top: auto; padding-top: 18px; color: #f0a440; font: 600 22px "Schibsted Grotesk", Arial, sans-serif; letter-spacing: 0.01em; }}
.shot {{ position: relative; overflow: hidden; }}
.shot img {{ position: absolute; top: 72px; left: 24px; width: 980px; border-radius: 10px;
            border: 1px solid #1d2e3f; box-shadow: 0 24px 60px rgba(0,0,0,0.45); }}
.shot::after {{ content: ""; position: absolute; inset: 0; background: linear-gradient(90deg, #0b1520 0%, rgba(11,21,32,0) 18%); }}
</style></head><body><div class="card">
<div class="text"><div class="mark"><img src="{icon}" alt="">Route Map</div><div class="rule"></div>
<h1>{headline}</h1><p>{line}</p><div class="url">getroutemap.app</div></div>
<div class="shot"><img src="{shot}" alt=""></div></div></body></html>"""


def render(chrome: str, name: str, headline: str, line: str) -> pathlib.Path:
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        page = pathlib.Path(tmp) / f"{name}.html"
        page.write_text(TEMPLATE.format(fonts=FONTS.as_uri(), icon=ICON.as_uri(), shot=SHOT.as_uri(),
                                        headline=html.escape(headline), line=html.escape(line)), encoding="utf-8")
        png = pathlib.Path(tmp) / f"{name}.png"
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--window-size=1200,630", "--virtual-time-budget=4000", f"--screenshot={png}", page.as_uri()],
                       check=True, capture_output=True)
        out = SITE / "assets" / "og" / f"{name}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.open(png).convert("RGB").resize((1200, 630)).save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args(argv)
    for name, (headline, line) in CARDS.items():
        print(render(args.chrome, name, headline, line))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
