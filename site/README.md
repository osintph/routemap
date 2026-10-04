# The project site (getroutemap.app)

`python site/build.py` builds it into `site/build/`; `.github/workflows/site.yml`
deploys it. Branding, links, contact and donations are in `site.toml`; page
text comes from the repository's own documents and `content/`; screenshots
are in `assets/shots/` as light and dark pairs taken from the real app.

**Style.** This must read as the product page of a tool that network and
security people trust, so it must never look like a template: no grids of
equal feature cards, no icon tiles, no numbered coloured circles, no gradient
washes or blobs, no glassmorphism, no stock imagery or illustration packs, no
emoji, and no marketing filler ("blazing fast", "seamless", "revolutionary").
The visuals are real screenshots and crops of the app; the copy is specific
(real hostnames, real numbers) and written for people who read traceroutes.
Newsreader for headings, Schibsted Grotesk for text (see Typography below);
one amber accent on navy; no cookies; every
page readable without JavaScript. Nothing is loaded from another server except
Cloudflare Web Analytics, which Cloudflare injects (cookieless, page totals
only); the CSP allows exactly that script host and nothing else, and the
privacy page says so. The desktop app itself has no telemetry. No em dashes.

## Typography

- **Headings:** Newsreader (Production Type), variable, weights 500 to 700,
  optical sizes 16 to 72.
- **Text, labels, buttons, eyebrows, badges:** Schibsted Grotesk (Schibsted),
  variable, weights 400 to 700.
- **Monospace, only for commands, code, trace output and hop tables:** IBM
  Plex Mono 400 and 500. Never for headings, body text or UI labels.

All three are under the SIL Open Font Licence 1.1 (texts beside the files in
`assets/fonts/`), self-hosted as WOFF2 with `font-display: swap`. Nothing is
loaded from Google Fonts or any other font service, so no visitor's address
goes to a third party. The files are subset to printable Latin (ASCII,
Latin-1, general punctuation, arrows); `tests/test_site.py` fails if a page
uses a character the fonts do not cover. To rebuild a subset from the
upstream font (github.com/google/fonts, ofl/), with fontTools and brotli:

    fonttools varLib.instancer "Newsreader[opsz,wght].ttf" wght=500:700 opsz=16:72 -o n.ttf
    pyftsubset n.ttf --unicodes="U+0020-007E,U+00A0-00FF,U+2010-2027,U+2030-203A,U+2190-2193,U+2212,U+20AC,U+2122" \
      --flavor=woff2 --layout-features="kern,liga,calt,ccmp,locl,mark,mkmk,onum,lnum,tnum,case,pnum" \
      --output-file=newsreader-var.woff2

**Banned on this site** (body, headings and UI), so a later round does not
bring them back: Inter, Geist, Space Grotesk, Plus Jakarta Sans, DM Sans,
Manrope, Outfit, Poppins, Satoshi, General Sans, and any other font that is
the default of a site generator, UI kit or template. Also retired here:
Archivo (the previous heading face). `tests/test_site.py` fails if a banned
family or a font service URL appears in the stylesheet or a built page.
