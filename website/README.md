# Website

The home page of Fuzzzy Law at https://law.fuzzzycore.com (also https://fuzzzylaw.web.app):
Georgian at `/`, English at `/en/`. Static HTML, one stylesheet, one small script, self-hosted
fonts.

What a visitor sees without opening anything: one line on what it is, a picture of how it works,
three steps each with its action (copy the address, pick your assistant, copy the two-line
message), an example answer, the live numbers, and a short safety strip. Everything longer (each
assistant's full steps, how it works, how fresh the data is, what is held, limits, privacy, all
free-help contacts, contributing) sits in closed sections that open on a tap. It works without JavaScript; the script only adds the copy buttons, the theme switch and
a refresh of the numbers. No cookies, no trackers, no requests to other sites except the
connector's coverage endpoint.

## Files

| Path | What |
|---|---|
| `src/ka/index.html`, `src/en/index.html` | the page in Georgian and English (same sections, same order; the build checks this) |
| `src/404.html` | the not-found page |
| `src/site.css`, `src/site.js` | the one stylesheet and the one script |
| `src/free-help.ka.html`, `src/free-help.en.html` | the free legal help contacts, each with the date it was checked; keep them the same as `backend/app/services/connector_reference.py` |
| `src/fonts/` | Inter, Noto Sans Georgian, Space Grotesk and Space Mono as woff2 (Latin or Georgian letters only), with their SIL Open Font Licence files |
| `src/law-names-en.json` | English names of the laws held (the coverage endpoint gives Georgian names only) |
| `src/site.json` | the site address, the coverage endpoint and the date the connect steps were checked |
| `src/robots.txt`, `src/sitemap.xml`, icons | copied as they are |
| `src/flutter_service_worker.js` | removes the offline worker an earlier app on this site left in some browsers |
| `build.py` | builds everything into `dist/` (Python 3 standard library only) |
| `firebase.json`, `.firebaserc` | Firebase Hosting: site `fuzzzylaw` in project `fuzzzylaws`, security headers, cache rules |

The "send this to your assistant" message is not copied by hand: `build.py` takes it from
`../docs/send-this.ka.md` and `../docs/send-this.en.md` (the text between the first pair of
```` ```text ```` fences), which are generated from the connector's code.

## Build

```bash
cd website
python3 build.py --no-our-gui            # the home page only, for a local look
python3 build.py --offline --no-our-gui  # the same, reusing the last coverage answer
```

The build fetches https://law-api.fuzzzycore.com/api/v1/connector/coverage once and writes the
numbers and dates into the pages (saved in `.cache/coverage.json`; `--coverage FILE` uses a saved
answer instead). It also fetches the article the example answer quotes (Labour Code, article 48,
paragraph 4) from the connector, so the example shows its real text, link and version date; it
stops if that paragraph no longer says what the example's summary line says. In the browser the page asks the same endpoint again at most once every six
hours; when it cannot reach it, the numbers from the build stay, with their date.

The build stops if the "How it stays current" facts no longer match what the connector reports,
if a placeholder is left in a page, or if the Georgian and English pages have different sections.

## Look at it locally

```bash
python3 -m http.server 8000 --directory dist                 # quick look
firebase serve --only hosting --port 5000 --project fuzzzylaws  # with the real headers
```

## The older app at /our-gui/

An earlier Flutter app of this project is kept at `/our-gui/`, unlisted: nothing links to it,
`robots.txt` disallows it, and it carries `noindex, nofollow` as a meta tag and as an
`X-Robots-Tag` header. Its source is not in this repository. Whoever deploys builds it from the
private repository's `frontend/` folder and passes the build to this script:

```bash
# in the private repository's frontend/ folder (Flutter 3.32.0)
fvm spawn 3.32.0 build web --release --target lib/main_production.dart --base-href /our-gui/

# here
python3 build.py --our-gui /path/to/frontend/build/web
```

`build.py` refuses to build without either `--our-gui PATH` or `--no-our-gui`, so a deploy cannot
drop `/our-gui/` by accident. It adds the noindex tag to the copied `index.html`. The old app's
build output is never committed here.

## Deploy

```bash
firebase hosting:channel:deploy <name> --expires 7d --project fuzzzylaws --no-authorized-domains  # preview
firebase deploy --only hosting --project fuzzzylaws                                               # live
```

Preview channels always send `X-Robots-Tag: noindex`, so check the `/our-gui/` header on the live
site or with `firebase serve`.

## Checks

Before a live deploy: the W3C HTML validator on `/`, `/en/` and `/404.html` (no errors); an axe or
Lighthouse accessibility check in both looks (no serious issues); Lighthouse mobile performance and
accessibility at least 95 in both languages; no horizontal scroll at 360 px wide, also with text at
200%; only same-site requests plus the coverage endpoint, and no cookies.
