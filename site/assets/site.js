// The site's only script, loaded in <head> so nothing flashes. Every page
// reads fully without it. It does two things, and sends nothing anywhere:
//  1. marks the visitor's platform on <html>, so the matching download button
//     is the one shown first;
//  2. the light/dark switch: follows the system until the visitor chooses,
//     then remembers the choice in localStorage (no cookie).
(function () {
  var root = document.documentElement;
  var ua = navigator.userAgent || "", p = "";
  if (/Windows/i.test(ua)) p = "windows";
  else if (/Macintosh|Mac OS X/i.test(ua) && !/iPhone|iPad/i.test(ua)) p = "macos";
  else if (/Linux|X11/i.test(ua) && !/Android/i.test(ua)) p = "linux";
  if (p) root.setAttribute("data-platform", p);

  var stored = null;
  try { stored = localStorage.getItem("theme"); } catch (e) {}
  if (stored === "light" || stored === "dark") root.setAttribute("data-theme", stored);

  function effective() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function syncPictures() {
    var t = root.getAttribute("data-theme");
    var sources = document.querySelectorAll("picture source[data-scheme]");
    for (var i = 0; i < sources.length; i++) {
      sources[i].media = !t ? "(prefers-color-scheme: dark)" : (t === "dark" ? "all" : "not all");
    }
  }
  function syncButton() {
    var b = document.getElementById("theme-toggle");
    if (!b) return;
    var dark = effective() === "dark";
    b.setAttribute("aria-pressed", dark ? "true" : "false");
    b.textContent = dark ? "Light mode" : "Dark mode";
  }
  document.addEventListener("DOMContentLoaded", function () {
    var b = document.getElementById("theme-toggle");
    if (b) {
      b.hidden = false;
      b.addEventListener("click", function () {
        var next = effective() === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        try { localStorage.setItem("theme", next); } catch (e) {}
        syncPictures(); syncButton();
      });
    }
    syncPictures(); syncButton();
    if (window.matchMedia) {
      var mq = matchMedia("(prefers-color-scheme: dark)");
      if (mq.addEventListener) mq.addEventListener("change", syncButton);
    }
  });
})();
