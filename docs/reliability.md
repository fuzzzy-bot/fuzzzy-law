# სანდოობა · Reliability

## მოკლედ

2026 წლის 21 ნოემბერს სერვისი დამოუკიდებლად შემოწმდა matsne.gov.ge-თან. კანონის ტექსტი ძალიან
სანდოა: 234 მუხლიდან (24-ვე კანონიდან) 234 სიტყვასიტყვით ემთხვევა matsne-ს, ძველი რედაქციებიდან
20-დან 20. 30 რეალური კითხვიდან 27-ზე სწორი პასუხი მიიღეს, 3-ზე ნაწილობრივ სწორი, არასწორი არც
ერთზე. ქვემოთ, ინგლისურად, არის დეტალები, ის, რაც გავასწორეთ, და ის, რაც ჯერ გასასწორებელია.

## The check

On 2026-11-21 one independent reviewer, who had not built the service, checked the live connector
against the official texts on matsne.gov.ge.

| What | Result |
|---|---|
| Current article text compared word for word with matsne (all 24 laws) | 234 of 234 identical |
| Article numbers, titles, links, version dates in those articles | all correct |
| Version date of each law against matsne's newest version | 24 of 24 equal |
| Earlier wordings compared with the matching matsne version (2016-2020 included) | 20 of 20 identical |
| Realistic questions (15 Georgian, 15 English; 4 with a false premise, 3 outside what is held), answered with the connector only | 27 correct (4 needed a second search in the law's own words), 3 partly correct, 0 wrong |
| Quote check (`verify_citation`) cases | 14 of 16 right; 1 wrong (see below), 1 misleading |
| Speed over 390 tool calls | median 0.38 s, 95th percentile 0.73 s, slowest 4.7 s; no errors |

The three partly correct answers depended on rules the service does not hold (subordinate acts) or
did not find.

## Fixed since

- An article number typed as `14^1` or `14 1` returned article 14 instead of 14¹. Now refused with a
  clear message (2026-11-21).
- The rules an assistant must follow were partly in a resource most assistants never load, and two
  of them contradicted each other on what to say when no court decision is found. They are now in the
  instructions every assistant receives, with one rule for "no decision found": *"I found no published
  decision on this in the collections this service holds, up to <date>; this does not mean none
  exists."* (2026-11-21)
- Past dates are now described honestly: the service returns the newest matsne version dated on or
  before the day, and a change in it may have taken effect later (2026-11-21).
- The free-help contacts gained the domestic-violence hotline 116 006, 112 first, and the right of
  every minor to free legal aid (2026-11-21).

## Known problems, not yet fixed

- **Past dates by entry into force.** matsne dates a version by the amending act, which can take
  effect later (the 2020 Labour Code reform, the 2018 Constitution). A few matsne versions are also
  dated out of order. The service says so, but does not yet answer by the day a change took effect.
- **Quote check and paragraphs.** `verify_citation` looks for a quote in the whole article, so a
  quote from another paragraph of the same article passes. Assistants are told to check the paragraph
  themselves.
- **Superscripts in court decisions.** Court texts lose raised digits ("381¹" reads "3811"), so the
  "law changed since the decision" note can name the wrong article for such numbers.
- **Search in everyday words** sometimes misses the key article ("my husband beats me" finds little;
  "domestic violence" in the law's words works), and the search's added terms are sometimes off the
  point. Assistants are told to search again in the law's own words.
- **Court decisions are not updated automatically** yet.
- Smaller items: a promulgation signature inside some laws' last article, missing article anchors in
  the Customs Code links, punctuation-only edits counted as changes.

## Limits of the check

234 of about 6,500 articles and 20 earlier wordings were compared in full; not every article or
version. The legal judgements on the 30 questions are a careful reader's, not a lawyer's. Legal-aid
phone numbers could not all be confirmed because some official sites did not answer.

## Request limits

One address can make 30 requests a minute (counted over the last 60 seconds, IPv6 by /64). AI
providers that call for many people from the same networks get 600 a minute per address. Request
bodies are limited to 64 KB. The reliability check met the limit five times while calling about once
every 2 seconds.
