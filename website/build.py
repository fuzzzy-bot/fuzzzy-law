#!/usr/bin/env python3
"""Build the Fuzzzy Law home page into website/dist/.

Python 3 standard library only. The same sources and the same coverage data always give
the same files.

    python3 build.py                      # fetch the coverage numbers, build, then refuse
                                          # to finish without the old app (see --our-gui)
    python3 build.py --our-gui PATH       # also copy the old Flutter app's web build to /our-gui/
    python3 build.py --no-our-gui         # build the home page only (local preview)
    python3 build.py --offline            # reuse the last fetched answers (.cache/)
    python3 build.py --coverage FILE      # use a saved coverage answer instead of fetching

What it does:
  1. Copies the CSS, the script and the fonts to dist/assets/ with a content hash in each
     name, so they can be cached for a year.
  2. Fetches the connector's coverage once and writes the numbers and dates into the pages.
     The pages may refresh the numbers later in the browser; these are the fallback. Also
     fetches the article the example answer quotes (Labour Code, article 48, paragraph 4), so
     the example always shows the connector's real text, link and version date.
  3. Puts the "send this to your assistant" message into the pages, taken from
     ../docs/send-this.ka.md and ../docs/send-this.en.md (the text between the first
     ```text fence pair). Until those files exist, an obvious placeholder is shown.
  4. Writes dist/index.html (Georgian), dist/en/index.html (English) and dist/404.html,
     plus robots.txt, sitemap.xml, icons and a clean-up worker for the old app's cache.
  5. With --our-gui, copies the old app into dist/our-gui/ and adds a noindex robots tag
     to its index.html.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
DIST = HERE / "dist"
CACHE = HERE / ".cache"
DOCS = HERE.parent / "docs"

KA_MONTHS = ["იანვარი", "თებერვალი", "მარტი", "აპრილი", "მაისი", "ივნისი", "ივლისი",
             "აგვისტო", "სექტემბერი", "ოქტომბერი", "ნოემბერი", "დეკემბერი"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]

# Facts the "How it stays current" text states; the build stops if the connector says otherwise.
EXPECTED_FACTS = ["01:17 UTC", "50 stored articles", "after 3 days", "10 seconds apart"]

# The example answer quotes this paragraph. Its one-line summary on the pages says "30 calendar
# days"; the build stops if the paragraph no longer says so.
EXAMPLE = {"code": "labour_code", "article": "48", "paragraph": "4",
           "must_contain": "30 კალენდარული დღის ვადაში"}

COPY_ICONS = (
    '<span class="btn__icons" aria-hidden="true">'
    '<svg class="ic" viewBox="0 0 24 24" focusable="false" data-icon-idle>'
    '<rect x="8" y="8" width="12" height="12"/><path d="M16 8V4H4v12h4"/></svg>'
    '<svg class="ic" viewBox="0 0 24 24" focusable="false" data-icon-done>'
    '<path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span>'
)
CHEVRON = ('<svg class="ic chev" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
           '<path d="M6 9l6 6 6-6"/></svg>')
# The "how it works" picture: thin-line icons and arrows. Each arrow has a wide-screen form
# (left to right) and a phone form (top to bottom); CSS shows one.
CHAT = ('<svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="M4 5h16v11H10l-5 4v-4H4z"/><path d="M8 9h8M8 12h5"/></svg>')
DOC = ('<svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
       '<path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5M9 12h7M9 15h7M9 18h4"/></svg>')
ARROWS_BOTH = (
    '<span class="flow__arrows" aria-hidden="true">'
    '<svg class="ic flow__h" viewBox="0 0 96 28" focusable="false">'
    '<path d="M4 8h84M80 3l8 5-8 5"/><path d="M92 20H8M16 15l-8 5 8 5"/></svg>'
    '<svg class="ic flow__v" viewBox="0 0 28 64" focusable="false">'
    '<path d="M8 4v52M3 48l5 8 5-8"/><path d="M20 60V8M15 16l5-8 5 8"/></svg></span>'
)
ARROW_BACK = (
    '<span class="flow__arrows" aria-hidden="true">'
    '<svg class="ic flow__h" viewBox="0 0 96 28" focusable="false">'
    '<path d="M92 14H8M16 9l-8 5 8 5"/></svg>'
    '<svg class="ic flow__v" viewBox="0 0 28 64" focusable="false">'
    '<path d="M14 60V8M9 16l5-8 5 8"/></svg></span>'
)

SEND_PLACEHOLDER = {
    "ka": "[ჩანაცვლების ადგილი: აქ იქნება მზა შეტყობინება. ის docs/send-this.ka.md ფაილიდან ჩაისმება.]",
    "en": "[Placeholder: the ready-made message goes here. It is taken from docs/send-this.en.md.]",
}
HELP_PLACEHOLDER = {
    "ka": '<p class="note">[ჩანაცვლების ადგილი: უფასო იურიდიული დახმარების დადასტურებული კონტაქტები.]</p>',
    "en": '<p class="note">[Placeholder: confirmed contacts for free legal help.]</p>',
}


def fail(message: str) -> None:
    print(f"build.py: {message}", file=sys.stderr)
    sys.exit(1)


def warn(message: str) -> None:
    print(f"build.py: warning: {message}", file=sys.stderr)


def short_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:10]


def hashed_name(rel: str, data: bytes) -> str:
    path = Path(rel)
    return str(path.with_name(f"{path.stem}.{short_hash(data)}{path.suffix}"))


def format_number(n: int, lang: str) -> str:
    sep = " " if lang == "ka" else ","
    return f"{n:,}".replace(",", sep)


def format_date(iso: str, lang: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not match:
        fail(f"not a date: {iso!r}")
    year, month, day = match.group(1), int(match.group(2)), int(match.group(3))
    if lang == "ka":
        return f"{year} წლის {day} {KA_MONTHS[month - 1]}"
    return f"{day} {EN_MONTHS[month - 1]} {year}"


# ---------------------------------------------------------------- coverage

def fetch_json(url: str, cache_name: str, offline: bool, given: str | None = None) -> dict:
    cached = CACHE / cache_name
    if given:
        raw = Path(given).read_bytes()
    elif offline:
        if not cached.exists():
            fail(f"--offline needs .cache/{cache_name} from an earlier build")
        raw = cached.read_bytes()
    else:
        request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                       "User-Agent": "fuzzzy-law-website-build"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except OSError as error:
            fail(f"could not fetch {url} ({error}); use --offline")
        CACHE.mkdir(exist_ok=True)
        cached.write_bytes(raw)
    try:
        return json.loads(raw)
    except ValueError:
        fail(f"the answer from {url} is not JSON")
    return {}


def load_coverage(args: argparse.Namespace, url: str) -> dict:
    return fetch_json(url, "coverage.json", args.offline, args.coverage)


def load_example(args: argparse.Namespace, coverage_url: str) -> dict:
    api = coverage_url.split("/api/", 1)[0]
    url = f"{api}/api/v1/connector/articles?code={EXAMPLE['code']}&article={EXAMPLE['article']}"
    data = fetch_json(url, "example-article.json", args.offline)
    article = data.get("article") or {}
    match = re.search(rf"(?m)^{EXAMPLE['paragraph']}\. (.+)$", article.get("text", ""))
    if not data.get("found") or not match:
        fail("the example article or its paragraph is missing from the connector's answer")
    quote = match.group(1).strip()
    if EXAMPLE["must_contain"] not in quote:
        fail("the example paragraph changed; update the example's summary line on both pages, "
             "then EXAMPLE['must_contain']")
    return {"quote": quote, "url": article["source_url"], "version_iso": article["version_date"],
            "law": article["code_name"]}


def coverage_values(cov: dict, lang: str, names_en: dict) -> dict:
    laws = cov.get("laws")
    courts = cov.get("court_decisions")
    if not isinstance(laws, list) or not laws or not isinstance(courts, list):
        fail("the coverage answer has no laws or court decisions")
    by_collection = {row["collection"]: row for row in courts}
    for key in ("court_practice", "grand_chamber", "constitutional_court"):
        if key not in by_collection:
            fail(f"the coverage answer has no {key} collection")
    kept = cov.get("how_data_is_kept") or []
    facts = " ".join(str(row.get(field, "")) for row in kept
                     for field in ("how_collected", "how_kept_current"))
    for fact in EXPECTED_FACTS:
        if fact not in facts:
            fail(f"'How it stays current' no longer matches the connector: {fact!r} is missing; "
                 "update the page text, then this list")
    court_dates = sorted(row.get("last_updated", "") for row in kept
                         if "Court" in str(row.get("data", "")))
    courts_updated = court_dates[0] if court_dates else cov["data_current_as_of"]

    values = {
        "laws": format_number(len(laws), lang),
        "articles": format_number(sum(int(law["article_count"]) for law in laws), lang),
        "asof_iso": cov["data_current_as_of"],
        "asof_text": format_date(cov["data_current_as_of"], lang),
        "courts_updated_iso": courts_updated,
        "courts_updated_text": format_date(courts_updated, lang),
        "warning_hidden": "" if cov.get("freshness_warning") else " hidden",
    }
    for key in ("court_practice", "grand_chamber", "constitutional_court"):
        values[key] = format_number(int(by_collection[key]["decision_count"]), lang)
    values["decisions"] = format_number(sum(int(row["decision_count"]) for row in courts), lang)
    if cov.get("freshness_warning"):
        warn("the connector reports stale data; the page shows its warning")

    def sort_key_ka(law: dict) -> str:
        return law["name"].removeprefix("საქართველოს ")

    rows = []
    if lang == "ka":
        for law in sorted(laws, key=sort_key_ka):
            rows.append(f'            <li><a href="{html.escape(law["source_url"])}">'
                        f'{html.escape(law["name"])}</a></li>')
    else:
        def english(law: dict) -> str:
            name = names_en.get(law["code"])
            if not name:
                warn(f"no English name for {law['code']}; using the Georgian one")
                return law["name"]
            return name
        for law in sorted(laws, key=english):
            rows.append(f'            <li><a href="{html.escape(law["source_url"])}">'
                        f'{html.escape(english(law))}</a>'
                        f'<span class="muted" lang="ka">{html.escape(law["name"])}</span></li>')
    values["law_list"] = "\n".join(rows)
    return values


# ---------------------------------------------------------------- the message

def send_this_block(lang: str) -> tuple[str, bool]:
    path = DOCS / f"send-this.{lang}.md"
    text = None
    if path.exists():
        match = re.search(r"```text[^\n]*\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)
        if match and match.group(1).strip():
            text = match.group(1).strip("\n")
        else:
            warn(f"{path.name} has no ```text block; showing the placeholder")
    else:
        warn(f"{path.name} does not exist yet; showing the placeholder")
    if text is None:
        body, extra = SEND_PLACEHOLDER[lang], " is-placeholder"
    else:
        body, extra = text, ""
    block = f'<pre class="message{extra}" id="send-text">{html.escape(body, quote=False)}</pre>'
    return block, text is not None


def free_help_block(lang: str) -> tuple[str, bool]:
    path = SRC / f"free-help.{lang}.html"
    if path.exists():
        return path.read_text(encoding="utf-8").rstrip("\n"), True
    warn(f"{path.name} does not exist yet; showing the placeholder")
    return "        " + HELP_PLACEHOLDER[lang], False


# ---------------------------------------------------------------- pages

PLACEHOLDER = re.compile(r"\{\{([a-z_]+)(?::([^}]+))?\}\}")


def render(template: str, lang: str, assets: dict, values: dict, extra: dict) -> str:
    def replace(match: re.Match) -> str:
        kind, arg = match.group(1), match.group(2)
        if kind == "asset":
            if arg not in assets:
                fail(f"unknown asset {arg}")
            return "/assets/" + assets[arg]
        if kind == "cov":
            if arg not in values:
                fail(f"unknown coverage value {arg}")
            return values[arg]
        if kind == "law_list":
            return values["law_list"]
        if kind == "icons":
            return {"copy": COPY_ICONS, "chevron": CHEVRON, "chat": CHAT, "doc": DOC,
                    "arrows-both": ARROWS_BOTH, "arrow-back": ARROW_BACK}[arg]
        if kind in extra:
            value = extra[kind]
            return value(arg) if callable(value) else value
        fail(f"unknown placeholder {match.group(0)}")
        return ""
    out = PLACEHOLDER.sub(replace, template)
    leftover = PLACEHOLDER.search(out)
    if leftover:
        fail(f"placeholder left in the page: {leftover.group(0)}")
    if "our-gui" in out:
        fail("a page mentions /our-gui/; it must be linked from nowhere")
    return out


def section_ids(page: str) -> list[str]:
    """Every id in the page, in order: the two languages must have the same structure."""
    return re.findall(r'\sid="([a-z0-9-]+)"', page)


# IndexNow (Bing, Yandex, Seznam, Naver): a public key file at the site root lets us tell
# those search engines when pages change, with no account. The key is public by design.
INDEXNOW_KEY_FILE = "11fad8a523a2e63253ca3812fef782fc.txt"


def build(args: argparse.Namespace) -> None:
    settings = json.loads((SRC / "site.json").read_text(encoding="utf-8"))
    names_en = json.loads((SRC / "law-names-en.json").read_text(encoding="utf-8"))["names"]

    if not args.our_gui and not args.no_our_gui:
        fail("give --our-gui PATH (the old app's web build) or --no-our-gui. A deploy "
             "without it would remove /our-gui/ from the site.")

    coverage = load_coverage(args, settings["coverage_url"])
    example = load_example(args, settings["coverage_url"])

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets" / "fonts").mkdir(parents=True)

    # Fonts first, so the stylesheet can point at their hashed names.
    assets: dict[str, str] = {}
    font_dir = SRC / "fonts"
    for font in sorted(font_dir.glob("*.woff2")):
        data = font.read_bytes()
        name = hashed_name(f"fonts/{font.name}", data)
        (DIST / "assets" / name).write_bytes(data)
        assets[f"fonts/{font.name}"] = name
    for licence in sorted(font_dir.glob("OFL-*.txt")):
        shutil.copyfile(licence, DIST / "assets" / "fonts" / licence.name)

    css = (SRC / "site.css").read_text(encoding="utf-8")
    for rel, name in assets.items():
        css = css.replace(f'url("{rel}")', f'url("{name}")')
    for ref in re.findall(r'url\("([^"]+)"\)', css):
        if ref not in assets.values():
            fail(f"site.css points at {ref}, which is not a font in src/fonts/")
    css_bytes = css.encode("utf-8")
    assets["site.css"] = hashed_name("site.css", css_bytes)
    (DIST / "assets" / assets["site.css"]).write_bytes(css_bytes)

    js_bytes = (SRC / "site.js").read_bytes()
    assets["site.js"] = hashed_name("site.js", js_bytes)
    (DIST / "assets" / assets["site.js"]).write_bytes(js_bytes)

    mark = (SRC / "mark.svg").read_text(encoding="utf-8").strip()
    mark = mark.replace(' xmlns="http://www.w3.org/2000/svg"', "")

    pages = {}
    report = {}
    for lang, src_rel, out_rel in (("ka", "ka/index.html", "index.html"),
                                   ("en", "en/index.html", "en/index.html")):
        values = coverage_values(coverage, lang, names_en)
        send_block, send_ok = send_this_block(lang)
        help_block, help_ok = free_help_block(lang)
        report[lang] = {"send_this": send_ok, "free_help": help_ok}
        extra = {
            "mark": mark,
            "send_this": send_block,
            "free_help": lambda _arg, block=help_block: block,
            "vendor_checked": format_date(settings["vendor_docs_checked"], lang),
            "example": lambda arg, lang=lang: {
                "quote": html.escape(example["quote"], quote=False),
                "url": html.escape(example["url"]),
                "version_iso": example["version_iso"],
                "version_text": format_date(example["version_iso"], lang),
            }[arg],
        }
        page = render((SRC / src_rel).read_text(encoding="utf-8"), lang, assets, values, extra)
        pages[lang] = page
        out = DIST / out_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")

    if section_ids(pages["ka"]) != section_ids(pages["en"]):
        fail(f"the Georgian and English pages have different sections: "
             f"{section_ids(pages['ka'])} vs {section_ids(pages['en'])}")

    not_found = render((SRC / "404.html").read_text(encoding="utf-8"), "ka", assets, {}, {"mark": mark})
    (DIST / "404.html").write_text(not_found, encoding="utf-8")

    for name in ("robots.txt", "favicon.svg", "favicon.png", "apple-touch-icon.png",
                 "icon-512.png", "og-ka.png", "og-en.png", "flutter_service_worker.js",
                 INDEXNOW_KEY_FILE):
        shutil.copyfile(SRC / name, DIST / name)

    # Ownership proofs other services read from fixed addresses (the MCP Registry's public key).
    shutil.copytree(SRC / ".well-known", DIST / ".well-known", dirs_exist_ok=True)

    # The sitemap tells search engines when the pages last changed: the build day.
    today = datetime.now(timezone.utc).date().isoformat()
    sitemap = (SRC / "sitemap.xml").read_text(encoding="utf-8")
    sitemap = re.sub(r"(<loc>[^<]+</loc>)", rf"\1\n    <lastmod>{today}</lastmod>", sitemap)
    (DIST / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    if args.our_gui:
        add_old_app(Path(args.our_gui))

    print(f"build.py: built {DIST.relative_to(HERE)}/ with coverage of "
          f"{coverage['data_current_as_of']}")
    for lang, parts in report.items():
        missing = [part for part, ok in parts.items() if not ok]
        if missing:
            print(f"build.py: {lang} page still has placeholders for: {', '.join(missing)}")


def add_old_app(source: Path) -> None:
    index = source / "index.html"
    if not index.exists():
        fail(f"{source} is not a Flutter web build (no index.html)")
    target = DIST / "our-gui"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".*"))
    page = (target / "index.html").read_text(encoding="utf-8")
    if '<base href="/our-gui/">' not in page:
        fail("the old app was not built with --base-href /our-gui/")
    tag = '<meta name="robots" content="noindex, nofollow">'
    if tag not in page:
        page = page.replace("<head>", "<head>\n  " + tag, 1)
    (target / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--our-gui", metavar="PATH", help="the old Flutter app's web build folder")
    parser.add_argument("--no-our-gui", action="store_true", help="build without the old app")
    parser.add_argument("--offline", action="store_true", help="reuse .cache/coverage.json")
    parser.add_argument("--coverage", metavar="FILE", help="use a saved coverage answer")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
