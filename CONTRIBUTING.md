# როგორ დაგვეხმარო · Contributing

[ქართული](#ქართული) · [English](#english)

## ქართული

მადლობა, რომ დახმარება გინდა. კოდის ცოდნა საჭირო არ არის.

### კოდის გარეშე

- **მუხლი არასწორია?** თუ ასისტენტმა ან სერვისმა მუხლის ტექსტი, ნომერი ან თარიღი არასწორად მოიყვანა,
  გახსენი [„არასწორი მუხლი“](https://github.com/fuzzzy-bot/fuzzzy-law/issues/new?template=wrong-article.yml).
  მიუთითე კანონი, მუხლი და, თუ გაქვს, matsne.gov.ge-ის ბმული.
- **ბმული არ მუშაობს?** გახსენი [„გატეხილი ბმული“](https://github.com/fuzzzy-bot/fuzzzy-law/issues/new?template=broken-link.yml).
- **ინსტრუქცია მოძველდა?** აპებმა მენიუ შეცვალეს? შეგვატყობინე იგივე გზით.
- **კანონი აკლია?** დაწერე, რომელი კანონი გჭირდება და რატომ ([იდეა](https://github.com/fuzzzy-bot/fuzzzy-law/issues/new?template=idea.yml)).
- **ქართული ტექსტი უცნაურად ჟღერს?** გვითხარი, როგორ ჯობს.

GitHub-ის ანგარიში არ გაქვს? მოგვწერე: support@fuzzzycore.com.
შენი პირადი საქმის დეტალები საჯარო შეტყობინებაში ნუ დაწერ.

### კოდით

იხილე ინგლისური ნაწილი ქვემოთ.

## English

Thank you for helping. You do not need to code.

### Without code

- **A wrong article?** If the service or an assistant quoted an article's text, number or date wrongly,
  open a [wrong article](https://github.com/fuzzzy-bot/fuzzzy-law/issues/new?template=wrong-article.yml)
  report with the law, the article and, if you have it, the matsne.gov.ge link.
- **A broken link?** Open a [broken link](https://github.com/fuzzzy-bot/fuzzzy-law/issues/new?template=broken-link.yml) report.
- **A guide out of date** because an app changed its menus? Report it the same way.
- **A law missing?** Tell us which and why in an [idea](https://github.com/fuzzzy-bot/fuzzzy-law/issues/new?template=idea.yml).
- **Georgian text that reads oddly?** Tell us how it should read.

No GitHub account? Write to support@fuzzzycore.com. Please never put details of your own legal
matter in a public issue.

### With code

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
2. Fork, branch from `main`, and keep each commit to one change in
   [Conventional Commits](https://www.conventionalcommits.org/) form: `feat`, `fix`, `refactor`,
   `docs` or `chore`, e.g. `fix(connector): keep the paragraph in quote checks`.
3. Run the tests and the linter for the part you changed (see the [README](README.md#for-developers)).
   CI runs the same, plus a secret scan.
4. If you change what the server tells assistants (`backend/app/services/connector_guidance.py`) or
   the REST API, run `python scripts/write_client_files.py` from `backend/` and commit the generated
   files; the tests fail when they drift.
5. Open a pull request and fill in the template.

Ground rules:

- The service returns sources and never writes advice. Do not add model calls to the server.
- Text from matsne.gov.ge and the courts is stored exactly as published. Never rewrite or summarise
  law text.
- Anything downloaded from an official site must be polite: robots.txt, one request at a time, at
  least 10 seconds apart, the project's user agent.
- No personal data in tests or fixtures: use invented names.
- No secrets in the repository. Report security problems privately (see [SECURITY.md](SECURITY.md)).

By contributing you agree that your contribution is licensed under the [MIT licence](LICENSE) and you
follow the [code of conduct](CODE_OF_CONDUCT.md).
