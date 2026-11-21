## What and why

<!-- One change per pull request. What does it do, and why? Link the issue if there is one. -->

## Checklist

- [ ] Commits follow Conventional Commits (`feat`, `fix`, `refactor`, `docs`, `chore`), one change each.
- [ ] Tests and `ruff check .` pass for the part I changed (`backend/`, `law_corpus/`).
- [ ] If I changed what the server tells assistants or the REST API, I ran
      `python scripts/write_client_files.py` and committed the generated files.
- [ ] No law text was rewritten; no personal data in tests or fixtures; no secrets.
- [ ] Anything that downloads from an official site stays polite (robots.txt, 10 s apart).
