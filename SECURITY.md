# Security · უსაფრთხოება

**ქართულად:** უსაფრთხოების პრობლემა იპოვე? საჯარო შეტყობინებას ნუ გახსნი. მოგვწერე
support@fuzzzycore.com-ზე, სათაურში „Security“, ან გამოიყენე GitHub-ის
[პირადი შეტყობინება](https://github.com/fuzzzy-bot/fuzzzy-law/security/advisories/new).

## Reporting a vulnerability

Please do not open a public issue. Write to **support@fuzzzycore.com** with "Security" in the subject,
or use GitHub's [private vulnerability reporting](https://github.com/fuzzzy-bot/fuzzzy-law/security/advisories/new).
Include what you found, how to reproduce it and what it affects. We will acknowledge your report,
keep you informed and credit you if you wish.

## Scope

- The connector at `https://law-api.fuzzzycore.com` and the code in this repository.
- The website `https://law.fuzzzycore.com`.

Please do not run load tests or automated scanners against the public service: it is small and
shared, and the request limits will block you. Test against your own copy instead
([run your own](docs/run-your-own.md)).

## Supported versions

Only the latest commit on `main`, which is what the public service runs.

## What the service holds

The connector is read-only, needs no account and stores no questions; its data is public law text and
published court decisions. See [privacy](docs/privacy.md).
