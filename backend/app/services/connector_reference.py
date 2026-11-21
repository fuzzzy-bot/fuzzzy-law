"""
Fixed reference facts the law connector hands out beside the stored law texts:
where a person can get free legal help in Georgia, what the connector does not
hold, and the law's own words for things people name in everyday speech.

These are written by hand, so each block carries the date a person last
checked it against its source. Nothing here is law text.
"""

from __future__ import annotations

# ── Free legal help ──────────────────────────────────────────
# Checked on the date below against legalaid.ge (contact page), ombudsman.ge
# and the Law of Georgia on Legal Aid (matsne.gov.ge document 21604).
LEGAL_AID_CHECKED_ON = "2026-11-14"

LEGAL_AID_PROVIDERS = [
    {
        "name": "იურიდიული დახმარების სამსახური (Legal Aid Service of Georgia)",
        "helps_with": (
            "State service. Free legal consultation on any legal question; drafting of "
            "documents and a lawyer in court for people who qualify."
        ),
        "free_for": (
            "Consultation: everyone. A lawyer at the state's expense: people registered "
            "as socially vulnerable (insolvent) and the other cases the law names; the "
            "service decides on application."
        ),
        "phone": "1485 (or 032 292 00 55)",
        "hours": "Phone consultation on working days, 10:00–18:00",
        "website": "https://www.legalaid.ge",
        "email": "info@legalaid.ge",
        "legal_basis": (
            "Law of Georgia on Legal Aid, articles 2, 5 and 17: "
            "https://matsne.gov.ge/ka/document/view/21604"
        ),
    },
    {
        "name": "საქართველოს სახალხო დამცველი (Public Defender of Georgia, Ombudsman)",
        "helps_with": (
            "Complaints that a state body, official or institution violated a person's "
            "rights: ill-treatment, unlawful detention, discrimination, domestic violence."
        ),
        "free_for": "Everyone.",
        "phone": "1481",
        "hours": "Hotline around the clock; office on working days, 9:00–18:00",
        "website": "https://www.ombudsman.ge",
        "email": "info@ombudsman.ge",
        "legal_basis": None,
    },
    {
        "name": "საქართველოს ახალგაზრდა იურისტთა ასოციაცია (Georgian Young Lawyers' Association)",
        "helps_with": "Non-governmental organisation that gives free legal consultations.",
        "free_for": "Everyone; see the website for its offices and current phone lines.",
        "phone": None,
        "hours": None,
        "website": "https://gyla.ge",
        "email": None,
        "legal_basis": None,
    },
]

LEGAL_AID_EMERGENCY = "In immediate danger call 112 (საგანგებო ნომერი 112)."

LEGAL_AID_MESSAGE = (
    "Give the person these contacts whenever the matter is serious, a deadline is "
    "running or they cannot pay a lawyer. Phone numbers and hours can change: tell "
    "them to confirm on the service's website. Do not promise that they qualify."
)

# ── What the connector does not hold ─────────────────────────
CONSTITUTIONAL_NOT_HELD = "Constitutional Court decisions."
NOT_COVERED = [
    "Laws that are not in the list of laws held; anything else is not held.",
    "Government and ministerial orders, municipal acts and other subordinate acts.",
    "Decisions of city (district) courts and courts of appeal.",
    "Supreme Court decisions the court did not print in its published collections: the "
    "collections are a selection the court makes, not every decision it made. That no "
    "stored decision matches is not proof that the court never ruled on a question.",
    CONSTITUTIONAL_NOT_HELD,
    "International treaties and judgments of the European Court of Human Rights.",
    "Draft laws, and amendments adopted but not yet in a consolidated version on matsne.",
]

# ── English names of the stored laws ─────────────────────────
# For the public coverage page only; the tools always give the Georgian name.
LAW_NAMES_EN = {
    "admin_offences_code": "Administrative Offences Code of Georgia",
    "admin_procedure_code": "Administrative Procedure Code of Georgia",
    "civil_code": "Civil Code of Georgia",
    "civil_procedure_code": "Civil Procedure Code of Georgia",
    "constitution": "Constitution of Georgia",
    "criminal_code": "Criminal Code of Georgia",
    "criminal_procedure_code": "Criminal Procedure Code of Georgia",
    "election_code": "Election Code of Georgia",
    "general_admin_code": "General Administrative Code of Georgia",
    "labour_code": "Labour Code of Georgia",
    "personal_data_law": "Law of Georgia on Personal Data Protection",
    "tax_code": "Tax Code of Georgia",
    "entrepreneurial_law": "Law of Georgia on Entrepreneurs",
    "consumer_rights_law": "Law of Georgia on the Protection of Consumer Rights",
    "customs_code": "Customs Code of Georgia",
    "legal_aid_law": "Law of Georgia on Legal Aid",
    "enforcement_law": "Law of Georgia on Enforcement Proceedings",
    "child_rights_code": "Code on the Rights of the Child of Georgia",
    "domestic_violence_law": (
        "Law of Georgia on the Elimination of Violence against Women and/or Domestic "
        "Violence and the Protection and Support of Victims"
    ),
    "anti_discrimination_law": "Law of Georgia on the Elimination of All Forms of Discrimination",
    "patient_rights_law": "Law of Georgia on the Rights of Patients",
    "juvenile_justice_code": "Juvenile Justice Code of Georgia",
    "social_assistance_law": "Law of Georgia on Social Assistance",
    "state_pension_law": "Law of Georgia on State Pensions",
}

# ── Everyday words → the law's own words ─────────────────────
# People ask in everyday Georgian; the codes use their own terms. When a
# question holds one of the word parts on the left, the search is also run
# with the phrase on the right. A search aid only: it never adds text to an
# answer.
PLAIN_TO_LAW_TERMS: list[tuple[tuple[str, ...], str]] = [
    (("სამსახურიდან", "სამუშაოდან", "დათხოვ", "გამათავისუფლ", "გამაგდ"),
     "შრომითი ხელშეკრულების შეწყვეტის საფუძვლები"),
    (("ხელფას",), "შრომის ანაზღაურების გაცემის დრო"),
    (("შვებულებ",), "ანაზღაურებადი შვებულების ხანგრძლივობა"),
    (("მემკვიდრეობის მიღ", "მემკვიდრეობა მივიღ", "მემკვიდრეობის ვად"), "სამკვიდროს მიღების ვადა"),
    (("ნასვამ", "მთვრალ"), "ალკოჰოლური სიმთვრალის მდგომარეობაში სატრანსპორტო საშუალების მართვა"),
    (("ქირა", "გამომასახლ", "გამოსახლ"), "ქირავნობის ხელშეკრულების მოშლა"),
    (("გაყრა", "გავეყარ", "გაყრის"), "ქორწინების შეწყვეტის საფუძვლები"),
    (("გაყრა", "გავეყარ", "გაყრის"), "განქორწინების საქმეთა განხილვა სასამართლოს მიერ"),
    (("ქონების გაყოფა", "ქონების გაყოფ"), "მეუღლეთა საერთო ქონების გაყოფა"),
    (("ვალი ", "ვალის ", "ვალს ", "ვალი?"), "ხელშეკრულების შეწყვეტა და ვალის დაბრუნება"),
    (("წუნი", "წუნდებულ", "ნაკლიან", "გაფუჭებულ"), "ნაკლის მქონე ნივთი"),
    (("მოტყუებ", "მომატყუ"), "თაღლითობა"),
    (("პირადი მონაცემ", "პირად მონაცემ"), "მონაცემთა დამუშავების საფუძვლები"),
    (("დამაკავ", "დააკავეს"), "დაკავების საფუძველი"),
    (("დამაკავ", "დააკავეს"), "ადმინისტრაციული დაკავება"),
    (("ბავშვის რჩენა", "ბავშვის სარჩო"), "შვილების რჩენის მოვალეობა"),
    (("ბავშვის რჩენა", "ბავშვის სარჩო", "ალიმენტ"),
     "ალიმენტის ოდენობის განსაზღვრა სასამართლოს მიერ"),
    (("მეურვე",), "ბავშვისთვის მეურვეობისა და მზრუნველობის დაწესება"),
]


def law_terms_for(query: str) -> list[str]:
    """The law's own phrases for the everyday words found in ``query``."""
    lowered = query.lower() + " "
    return [phrase for triggers, phrase in PLAIN_TO_LAW_TERMS
            if any(trigger in lowered for trigger in triggers) and phrase not in query]


# ── Where the data comes from and how it is kept current ─────
# Shown by get_coverage and on the coverage page. Keep in step with
# law_corpus/scripts/daily_refresh.py, law_history.py, fetch_supreme_court_collections.py,
# extract_supreme_collections.py and fetch_constitutional_court.py.
POLITE_COLLECTION = (
    "Downloaded the way the site allows: its robots.txt rules are followed, one request "
    "at a time, at least 10 seconds apart."
)
DATA_SOURCES = {
    "laws": {
        "data": "Law texts (current version)",
        "source": "matsne.gov.ge, the Legislative Herald of Georgia",
        "source_url": "https://matsne.gov.ge",
        "how_collected": (
            "Each law's current consolidated version is downloaded from its official page "
            "and stored article by article, word for word, with the page's link and the "
            "version date. Nothing is rewritten or summarised. " + POLITE_COLLECTION
        ),
        "how_kept_current": (
            "Every night at 01:17 UTC (05:17 in Tbilisi) every law's page is downloaded "
            "again. A law whose page shows a new version, or any line that differs, is read "
            "again; the new texts are checked against the pages (every article present, "
            "every line word for word) and only then replace the old ones. Each night 50 "
            "stored articles chosen at random are also compared with matsne word for word. "
            "If a check fails, the last confirmed texts stay in place; after 3 days without "
            "a successful check every answer carries a warning. Amendments that are adopted "
            "but not yet in a consolidated version on matsne are not held."
        ),
    },
    "history": {
        "data": "Earlier wordings of articles",
        "source": "matsne.gov.ge, earlier consolidated versions of each law",
        "source_url": "https://matsne.gov.ge",
        "how_collected": (
            "Every consolidated version matsne publishes for a law since the version in "
            "force at the start of 2016 (later for laws adopted later) is downloaded from its "
            "own official page and stored article by article, so an article can be read as "
            "it stood on a given date. " + POLITE_COLLECTION
        ),
        "how_kept_current": (
            "Each night a new version of a law found on matsne is added. Stored earlier "
            "versions do not change."
        ),
    },
    "court_practice": {
        "data": "Supreme Court decisions (including the Grand Chamber)",
        "source": "supremecourt.ge, the court's published collections of decisions",
        "source_url": "https://www.supremecourt.ge",
        "how_collected": (
            "Taken from the collections the Supreme Court publishes (civil, criminal and "
            "administrative chambers and the Grand Chamber), where the court prints the "
            "parties as initials. Each decision is stored as printed, with a link to the "
            "page of the collection it starts on. A decision that still names private people "
            "in full is left out. Collection files that are no longer online (mostly "
            "2000-2007) could not be included. " + POLITE_COLLECTION
        ),
        "how_kept_current": (
            "Not yet updated automatically: new collections are added when the store is "
            "rebuilt. last_updated is the date of the last rebuild; decisions published "
            "after it are not held."
        ),
    },
    "constitutional_court": {
        "data": "Constitutional Court judgments",
        "source": "constcourt.ge, the Constitutional Court's published acts",
        "source_url": "https://www.constcourt.ge",
        "how_collected": (
            "The court's published judgments (გადაწყვეტილება), stored as the court "
            "published them, with the parties' names as the court prints them and a link to "
            "each judgment's page. " + POLITE_COLLECTION
        ),
        "how_kept_current": (
            "Not yet updated automatically: new judgments are added when the store is "
            "rebuilt. last_updated is the date of the last rebuild."
        ),
    },
}
