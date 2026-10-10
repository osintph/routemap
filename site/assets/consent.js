// Google Analytics on getroutemap.app, only with the visitor's consent.
//
// Nothing from Google loads until the visitor presses "Accept analytics
// cookies" in the banner: no script, no cookie, no request ("basic consent
// mode", developers.google.com/tag-platform/security/concepts/consent-mode).
// "Reject" loads nothing, now or later. The choice is kept in localStorage
// (not a cookie) and can be changed from "Cookie settings" in the footer;
// withdrawing it deletes Google Analytics' cookies and reloads the page, so
// no Google script keeps running.
//
// After consent: the consent state (analytics granted, advertising denied),
// then the standard gtag.js setup (developers.google.com/tag-platform/
// gtagjs/install), run from this file instead of an inline script, and one
// event per download link click, so Analytics and the server's download log
// can be compared.
//
// The measurement ID comes from <meta name="ga-measurement-id">, which the
// site builder writes only when site.toml sets one. Without it this script
// does nothing.
(function () {
  var KEY = "analytics-consent";
  var meta = document.querySelector('meta[name="ga-measurement-id"]');
  var id = meta && meta.getAttribute("content");
  if (!id || !/^G-[A-Z0-9]{4,20}$/.test(id)) return;

  var loaded = false;

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function store(value) {
    try { localStorage.setItem(KEY, value); } catch (e) {}
  }

  function load() {
    if (loaded) return;
    loaded = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    // The visitor accepted analytics, and only analytics: consent for
    // measurement is granted, everything for advertising denied. It must come
    // before any command that sends data, such as config
    // (developers.google.com/tag-platform/security/guides/consent).
    window.gtag("consent", "default", {
      analytics_storage: "granted",
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied"
    });
    window.gtag("js", new Date());
    window.gtag("config", id);
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id);
    document.head.appendChild(s);
  }

  // _ga and _ga_<container> on this host and its parent domain.
  function deleteCookies() {
    var names = document.cookie.split(";").map(function (c) { return c.split("=")[0].trim(); });
    var host = location.hostname;
    var domains = ["", host, "." + host, "." + host.split(".").slice(-2).join(".")];
    names.forEach(function (name) {
      if (name !== "_ga" && name.indexOf("_ga_") !== 0) return;
      domains.forEach(function (d) {
        document.cookie = name + "=; Max-Age=0; Path=/" + (d ? "; Domain=" + d : "") + "; SameSite=Lax";
      });
    });
  }

  function platform(file) {
    if (/^SHA256SUMS(\.asc|\.ed25519)?$/.test(file)) return "checksums";
    var m = /-(windows|macos|linux)-/.exec(file);
    return m ? m[1] : "other";
  }

  // /dl/<tag>/<file>: one event per click, after consent only.
  function onClick(ev) {
    if (!loaded) return;
    var a = ev.target.closest && ev.target.closest('a[href^="/dl/"]');
    if (!a) return;
    var parts = a.getAttribute("href").split("/");
    if (parts.length !== 4) return;
    window.gtag("event", "routemap_download", {
      file: parts[3].slice(0, 100),
      platform: platform(parts[3]),
      version: parts[2].replace(/^v/, "").slice(0, 100)
    });
  }

  function decide(value, banner) {
    var before = stored();
    store(value);
    banner.hidden = true;
    if (value === "granted") {
      load();
    } else if (before === "granted" || loaded) {
      deleteCookies();
      location.reload();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var banner = document.getElementById("consent");
    if (!banner) return;
    var choice = stored();
    if (choice === "granted") load();
    else if (choice !== "denied") banner.hidden = false;
    banner.querySelector('[data-consent="granted"]').addEventListener("click", function () { decide("granted", banner); });
    banner.querySelector('[data-consent="denied"]').addEventListener("click", function () { decide("denied", banner); });
    var links = document.querySelectorAll("[data-cookie-settings]");
    for (var i = 0; i < links.length; i++) {
      links[i].addEventListener("click", function (ev) {
        ev.preventDefault();
        banner.hidden = false;
        var first = banner.querySelector("button");
        if (first) first.focus();
      });
    }
    document.addEventListener("click", onClick, true);
  });
})();
