/* Fuzzzy Law home page: copy buttons, the theme switch and a gentle refresh of the numbers.
   The page works without this file: the numbers come from the build, the steps are plain
   text and the address can be selected by hand. No cookies, no trackers. Browser storage
   holds only the theme choice and the last numbers, and every read and write is guarded. */
(function () {
  "use strict";

  var root = document.documentElement;
  var THEME_KEY = "fuzzzy-law-theme";
  var NUMBERS_KEY = "fuzzzy-law-coverage";
  var COVERAGE_URL = "https://law-api.fuzzzycore.com/api/v1/connector/coverage";
  var SIX_HOURS = 6 * 60 * 60 * 1000;

  function read(key) {
    try { return window.localStorage.getItem(key); } catch (e) { return null; }
  }
  function write(key, value) {
    try { window.localStorage.setItem(key, value); } catch (e) { /* storage blocked: fine */ }
  }

  /* Theme: apply a saved choice before the page paints (this file loads in the head). */
  var savedTheme = read(THEME_KEY);
  if (savedTheme === "light" || savedTheme === "dark") root.setAttribute("data-theme", savedTheme);

  function systemDark() {
    try { return window.matchMedia("(prefers-color-scheme: dark)").matches; } catch (e) { return false; }
  }
  function isDark() {
    var chosen = root.getAttribute("data-theme");
    return chosen ? chosen === "dark" : systemDark();
  }

  function setupTheme() {
    var button = document.querySelector("[data-theme-toggle]");
    if (!button) return;
    var sync = function () { button.setAttribute("aria-pressed", isDark() ? "true" : "false"); };
    button.addEventListener("click", function () {
      var next = isDark() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      write(THEME_KEY, next);
      sync();
    });
    try {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", sync);
    } catch (e) { /* older browsers: the button still works */ }
    sync();
    button.hidden = false;
  }

  /* Copy buttons: data-copy names the element whose text is copied, or data-copy-text holds it. */
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.className = "sr-only";
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(area);
      if (ok) resolve(); else reject(new Error("copy failed"));
    });
  }

  function setupCopy() {
    var status = document.getElementById("copy-status");
    var buttons = document.querySelectorAll("[data-copy], [data-copy-text]");
    Array.prototype.forEach.call(buttons, function (button) {
      var timer = null;
      button.addEventListener("click", function () {
        var text = button.getAttribute("data-copy-text");
        if (!text) {
          var source = document.getElementById(button.getAttribute("data-copy"));
          text = source ? source.textContent.replace(/^\s+|\s+$/g, "") : "";
        }
        if (!text) return;
        copyText(text).then(function () {
          button.setAttribute("data-state", "done");
          if (status) status.textContent = button.getAttribute("data-copied-note") || "";
          clearTimeout(timer);
          timer = setTimeout(function () {
            button.removeAttribute("data-state");
            if (status) status.textContent = "";
          }, 2400);
        }, function () {
          if (status) status.textContent = button.getAttribute("data-failed-note") || "";
        });
      });
      button.hidden = false;
    });
  }

  /* Numbers: the build put them in the page. Ask the connector again at most once every six
     hours per browser; when it cannot be reached, the build's numbers and date stay. */
  var KA_MONTHS = ["იანვარი", "თებერვალი", "მარტი", "აპრილი", "მაისი", "ივნისი", "ივლისი",
    "აგვისტო", "სექტემბერი", "ოქტომბერი", "ნოემბერი", "დეკემბერი"];
  var EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"];

  function lang() { return (root.getAttribute("lang") || "en").slice(0, 2); }

  function formatNumber(n) {
    var s = String(Math.round(n));
    var sep = lang() === "ka" ? " " : ",";
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, sep);
  }
  function formatDate(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!m) return null;
    var y = m[1], mo = parseInt(m[2], 10) - 1, d = parseInt(m[3], 10);
    if (mo < 0 || mo > 11) return null;
    return lang() === "ka" ? y + " წლის " + d + " " + KA_MONTHS[mo] : d + " " + EN_MONTHS[mo] + " " + y;
  }

  function summarize(data) {
    if (!data || !Array.isArray(data.laws) || !Array.isArray(data.court_decisions)) return null;
    var asof = typeof data.data_current_as_of === "string" ? data.data_current_as_of : null;
    if (!formatDate(asof)) return null;
    var articles = 0;
    for (var i = 0; i < data.laws.length; i++) {
      var c = data.laws[i] && data.laws[i].article_count;
      if (typeof c !== "number" || c < 0) return null;
      articles += c;
    }
    var courts = {};
    data.court_decisions.forEach(function (row) {
      if (row && typeof row.collection === "string" && typeof row.decision_count === "number") {
        courts[row.collection] = row.decision_count;
      }
    });
    return {
      asof: asof,
      warn: !!data.freshness_warning,
      laws: data.laws.length,
      articles: articles,
      courts: courts
    };
  }

  function apply(summary) {
    if (!summary) return;
    var values = { laws: summary.laws, articles: summary.articles };
    Object.keys(summary.courts).forEach(function (k) { values[k] = summary.courts[k]; });
    Array.prototype.forEach.call(document.querySelectorAll("[data-cov]"), function (el) {
      var key = el.getAttribute("data-cov");
      if (key === "asof") {
        var text = formatDate(summary.asof);
        if (text) { el.textContent = text; el.setAttribute("datetime", summary.asof); }
      } else if (typeof values[key] === "number") {
        el.textContent = formatNumber(values[key]);
      }
    });
    var warning = document.querySelector("[data-cov-warning]");
    if (warning) warning.hidden = !summary.warn;
  }

  function setupNumbers() {
    var holder = document.querySelector("[data-cov-built]");
    if (!holder) return;
    var builtAsOf = holder.getAttribute("data-cov-built");
    var cached = null;
    try { cached = JSON.parse(read(NUMBERS_KEY) || "null"); } catch (e) { cached = null; }
    if (cached && cached.summary && typeof cached.summary.asof === "string" && cached.summary.asof >= builtAsOf) {
      apply(cached.summary);
    }
    var now = Date.now();
    var last = cached && typeof cached.at === "number" ? cached.at : 0;
    if (last && last <= now && now - last < SIX_HOURS) return;
    if (!window.fetch) return;

    var keep = cached && cached.summary ? cached.summary : null;
    write(NUMBERS_KEY, JSON.stringify({ at: now, summary: keep }));
    var controller = window.AbortController ? new AbortController() : null;
    var stop = controller ? setTimeout(function () { controller.abort(); }, 8000) : null;
    fetch(COVERAGE_URL, { mode: "cors", credentials: "omit", signal: controller ? controller.signal : undefined })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error(String(r.status))); })
      .then(function (data) {
        var summary = summarize(data);
        if (!summary) return;
        write(NUMBERS_KEY, JSON.stringify({ at: now, summary: summary }));
        if (summary.asof >= builtAsOf) apply(summary);
      })
      .catch(function () { /* unreachable: the dated numbers from the build stay */ })
      .then(function () { if (stop) clearTimeout(stop); });
  }

  function start() {
    setupTheme();
    setupCopy();
    setupNumbers();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
