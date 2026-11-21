"""
Public coverage page — what the law connector holds, as one plain web page.

Built from the same answers the tools give (``get_coverage`` and
``find_legal_aid``), so the page cannot say more than the connector holds.
One self-contained document: no script, no outside font, image or request.
Every value is escaped before it is written into the page.
"""

from __future__ import annotations

from html import escape

from app.schemas.connector_schema import CoverageResult, LegalAidResult
from app.services.connector_reference import LAW_NAMES_EN

PAGE_TITLE = "Fuzzzy Law — what the Georgian law connector holds"
PAGE_DESCRIPTION = (
    "Which Georgian laws and court decisions the free Fuzzzy Law connector holds, "
    "how current they are, and what it does not hold."
)
OPERATOR = "Fuzzy Core LLC"
CONTACT_EMAIL = "support@fuzzzycore.com"
# The page carries its own style block and nothing else may load or frame it.
PAGE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
    "Cache-Control": "public, max-age=300",
}

_STYLE = """
:root{--ground:#f2f0e9;--surface:#f8f7f2;--ink:#1c1b15;--mute:#6b6961;--line:#d6d4cc;--mark:#a32218}
@media (prefers-color-scheme:dark){:root{--ground:#0b0c0f;--surface:#14161b;--ink:#eef0f4;
--mute:#a3a7b0;--line:#2a2d35;--mark:#ff8a7a}}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);line-height:1.55;
font:16px/1.55 "Inter","Noto Sans Georgian",system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:60rem;margin:0 auto;padding:2.5rem 1rem 4rem}
h1{font-size:1.9rem;line-height:1.2;margin:0 0 .75rem}
h2{font-size:1.25rem;margin:2.75rem 0 .75rem}
p{margin:.6rem 0;max-width:44rem}
a{color:inherit;text-underline-offset:.15em}
a:focus-visible{outline:2px solid var(--mark);outline-offset:2px}
.lead{font-size:1.1rem}
.note{color:var(--mute);font-size:.92rem}
.stamp,.warn,.card{background:var(--surface);border:1px solid var(--line);border-radius:6px;
padding:.75rem 1rem;margin:1rem 0;max-width:44rem}
.warn{border-color:var(--mark)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.95rem}
th,td{text-align:left;vertical-align:top;padding:.6rem 1rem;border-top:1px solid var(--line)}
thead th{border-top:0}
th[scope=col]{font-size:.8rem;letter-spacing:.04em;text-transform:uppercase;color:var(--mute);
white-space:nowrap}
td.num{white-space:nowrap;font-variant-numeric:tabular-nums}
.sub{display:block;color:var(--mute);font-size:.88rem}
code{font:0.92em ui-monospace,"Space Mono",Menlo,monospace;background:var(--surface);
border:1px solid var(--line);border-radius:4px;padding:.1em .35em;overflow-wrap:anywhere}
ul{padding-left:1.2rem;max-width:44rem}
li{margin:.3rem 0}
dl{margin:.4rem 0 0}
dt{color:var(--mute);font-size:.85rem;margin-top:.45rem}
dd{margin:0}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--line)}
"""


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _link(url: str, label: str) -> str:
    return f'<a href="{_text(url)}" rel="noopener noreferrer">{_text(label)}</a>'


def _law_rows(coverage: CoverageResult) -> str:
    rows = []
    for law in coverage.laws:
        english = LAW_NAMES_EN.get(law.code)
        name = f'<span lang="ka">{_text(law.name)}</span>'
        if english:
            name += f'<span class="sub">{_text(english)}</span>'
        if law.history_from:
            earlier = (f"from {_text(law.history_from)}"
                       f'<span class="sub">{law.history_versions} versions</span>')
        else:
            earlier = "current text only"
        rows.append(
            f'<tr><th scope="row">{name}</th>'
            f'<td class="num">{law.article_count}</td>'
            f'<td class="num">{_text(law.version_date or "not dated")}</td>'
            f'<td class="num">{earlier}</td>'
            f"<td>{_link(law.source_url, 'matsne.gov.ge')}</td></tr>"
        )
    return "".join(rows)


def _court_rows(coverage: CoverageResult) -> str:
    rows = []
    for court in coverage.court_decisions:
        if court.earliest and court.latest:
            span = f"{_text(court.earliest)} to {_text(court.latest)}"
        else:
            span = "not dated"
        rows.append(
            f'<tr><th scope="row">{_text(court.court)}</th>'
            f'<td class="num">{court.decision_count}</td>'
            f'<td class="num">{span}</td></tr>'
        )
    return "".join(rows)


def _source_cards(coverage: CoverageResult) -> str:
    cards = []
    for note in coverage.how_data_is_kept:
        updated = note.last_updated or "not recorded"
        cards.append(
            f'<div class="card"><strong>{_text(note.data)}</strong>'
            f"<dl><dt>Source</dt><dd>{_link(note.source_url, note.source)}</dd>"
            f"<dt>How it is collected</dt><dd>{_text(note.how_collected)}</dd>"
            f"<dt>How it is kept current</dt><dd>{_text(note.how_kept_current)}</dd>"
            f"<dt>Last updated</dt><dd>{_text(updated)}</dd></dl></div>"
        )
    return "".join(cards)


def _aid_cards(aid: LegalAidResult) -> str:
    cards = []
    for provider in aid.providers:
        facts = [("Free for", provider.free_for)]
        if provider.phone:
            facts.append(("Phone", provider.phone))
        if provider.hours:
            facts.append(("Hours", provider.hours))
        if provider.email:
            facts.append(("Email", provider.email))
        listed = "".join(f"<dt>{_text(k)}</dt><dd>{_text(v)}</dd>" for k, v in facts)
        cards.append(
            f'<div class="card"><strong>{_text(provider.name)}</strong>'
            f"<p>{_text(provider.helps_with)}</p><dl>{listed}"
            f"<dt>Website</dt><dd>{_link(provider.website, provider.website)}</dd></dl></div>"
        )
    return "".join(cards)


def render_coverage_page(coverage: CoverageResult, aid: LegalAidResult, public_url: str) -> str:
    """The coverage page as one HTML document.

    ``public_url`` is the origin the connector is reached at; the page prints
    the connector address under it.
    """
    endpoint = public_url.rstrip("/") + "/mcp"
    if coverage.data_current_as_of:
        stamp = (f"The stored law texts were last confirmed against matsne.gov.ge on "
                 f"<strong>{_text(coverage.data_current_as_of)}</strong>. "
                 f"They are checked once a day.")
    else:
        stamp = "The date of the last check against matsne.gov.ge is not known."
    warning = (f'<p class="warn" role="note">{_text(coverage.freshness_warning)}</p>'
               if coverage.freshness_warning else "")
    not_held = "".join(f"<li>{_text(item)}</li>" for item in coverage.not_covered)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_text(PAGE_TITLE)}</title>
<meta name="description" content="{_text(PAGE_DESCRIPTION)}">
<meta name="referrer" content="no-referrer">
<style>{_STYLE}</style>
</head>
<body>
<main>
<h1>Georgian law for AI assistants</h1>
<p class="lead">A free connector that gives an AI assistant the exact text of Georgian laws
and published court decisions, each with its official link and version date, so the
assistant quotes the law instead of guessing it.</p>
<p>This is legal information, not legal advice. The official text of a law is the one on
{_link("https://matsne.gov.ge", "matsne.gov.ge")}.</p>
<p class="stamp">{stamp}</p>
{warning}

<h2 id="laws">Laws held</h2>
<p class="note" id="laws-note">Each law is stored in its current consolidated version.
Where earlier versions are stored, an article can also be read in the newest version
dated on or before an earlier day (a change can take effect later than its version date).</p>
<div class="scroll"><table aria-labelledby="laws" aria-describedby="laws-note">
<thead><tr><th scope="col">Law</th><th scope="col">Articles</th>
<th scope="col">Version stored</th><th scope="col">Earlier wordings</th>
<th scope="col">Official text</th></tr></thead>
<tbody>{_law_rows(coverage)}</tbody>
</table></div>

<h2 id="courts">Court decisions held</h2>
<p class="note" id="courts-note">Decisions are stored in the form the court published
them. This is a part of each court's practice, not all of it.</p>
<div class="scroll"><table aria-labelledby="courts" aria-describedby="courts-note">
<thead><tr><th scope="col">Court</th><th scope="col">Decisions</th>
<th scope="col">Dated</th></tr></thead>
<tbody>{_court_rows(coverage)}</tbody>
</table></div>

<h2 id="sources">Where the data comes from and how it stays current</h2>
<p>Everything is taken from the official publishers and stored as they publish it.
No text is written or changed by AI.</p>
{_source_cards(coverage)}

<h2 id="not-held">Not held</h2>
<p>When a question needs one of these, the connector says so and the assistant is told
not to answer it from memory.</p>
<ul>{not_held}</ul>

<h2 id="connect">Connecting an assistant</h2>
<p>The connector speaks the Model Context Protocol. Add this address as a custom
connector in an assistant that supports it:</p>
<p><code>{_text(endpoint)}</code></p>
<p class="note">No account and no key are needed. Search matches the words of the law,
so a question works best in Georgian legal terms.</p>

<h2 id="privacy">What is kept</h2>
<p>The service does not store what people ask. Its server log keeps the caller's network
address and which path was called for seven days, to handle abuse. The question itself
is never in it.</p>

<h2 id="help">Free legal help in Georgia</h2>
<p>{_text(aid.emergency)}</p>
{_aid_cards(aid)}
<p class="note">Contacts last checked on {_text(aid.checked_on)}. Phone numbers and hours
can change; confirm them on each service's website.</p>

<footer class="note">
<p>Run by {_text(OPERATOR)}. Contact: {_link("mailto:" + CONTACT_EMAIL, CONTACT_EMAIL)}.</p>
</footer>
</main>
</body>
</html>
"""
