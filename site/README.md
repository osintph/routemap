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
One display face (Archivo) and one text face (IBM Plex Sans, with Plex Mono
for trace output), self-hosted; one amber accent on navy; no cookies; every
page readable without JavaScript. Nothing is loaded from another server except
Cloudflare Web Analytics, which Cloudflare injects (cookieless, page totals
only); the CSP allows exactly that script host and nothing else, and the
privacy page says so. The desktop app itself has no telemetry. No em dashes.
