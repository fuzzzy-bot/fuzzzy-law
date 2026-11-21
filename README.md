# Fuzzzy Law

**საქართველოს კანონები შენი AI ასისტენტისთვის. Georgian law for your AI assistant.**

[ქართული](#ქართული) · [English](#english) · [For developers](#for-developers)

Website: https://law.fuzzzycore.com (also https://fuzzzylaw.web.app) · Connector address: `https://law-api.fuzzzycore.com/mcp`

---

## ქართული

### რა არის ეს

Fuzzzy Law უფასო კონექტორია, რომელიც შენს AI ასისტენტს (ChatGPT, Claude, Gemini და სხვები)
საქართველოს კანონების ზუსტ ტექსტს აწვდის. ასისტენტი პასუხს კანონის ზუსტი სიტყვებით წერს,
matsne.gov.ge-ის ოფიციალური ბმულით და რედაქციის თარიღით. ძველ რედაქციებსა და სასამართლოების
გამოქვეყნებულ გადაწყვეტილებებსაც პოულობს.

უფასოა. ანგარიში არ სჭირდება. ჩვენი სერვერი AI-ს არ იძახებს: პასუხს შენი ასისტენტი წერს, ჩვენ
მხოლოდ წყაროს ვაძლევთ.

### ვისთვისაა

ყველასთვის, ვისაც საქართველოს კანონზე კითხვა აქვს: სამსახურიდან გაგათავისუფლეს, ხელფასს არ
გიხდიან, ალიმენტი, ჯარიმა, ქირა, ძალადობა. ასევე სტუდენტებისთვის, იურისტებისთვის და
დეველოპერებისთვის, რომლებსაც კანონის ზუსტი ტექსტი სჭირდებათ.

### დაკავშირება 2 წუთში

1. დააკოპირე კონექტორის მისამართი: `https://law-api.fuzzzycore.com/mcp`
2. დაამატე შენს ასისტენტში: [Claude](docs/connect/claude.md) · [ChatGPT](docs/connect/chatgpt.md) ·
   [Gemini](docs/connect/gemini.md) · [სხვა აპები](docs/connect/other-apps.md)
3. ახალ საუბარში ჩასვი და გაგზავნე ეს ტექსტი: [გაუგზავნე შენს ასისტენტს](docs/send-this.ka.md)

მერე უბრალოდ დასვი კითხვა, მაგალითად: „გუშინ სამსახურიდან გამათავისუფლეს და მიზეზი არ
დამიწერეს. რა ვადაში ვიჩივლო?“

### რა ინახება

2026 წლის 21 ნოემბრის მდგომარეობით:

- **24 კანონი**, 6,517 მუხლი: კონსტიტუცია, სამოქალაქო, სისხლის, შრომის, საგადასახადო,
  ადმინისტრაციული და საპროცესო კოდექსები, ოჯახში ძალადობის, იურიდიული დახმარების, პაციენტის
  უფლებების, პერსონალურ მონაცემთა დაცვის, სოციალური დახმარების, პენსიის და სხვა კანონები.
  სრული სია: https://law-api.fuzzzycore.com/coverage
- **ადრინდელი რედაქციები** დაახლოებით 2016 წლიდან (ზოგ კანონზე უფრო ადრიდანაც).
- **8,473 სასამართლო გადაწყვეტილება**: უზენაესი სასამართლოს 8,116 (2004-2026, მისი
  გამოქვეყნებული კრებულებიდან), დიდი პალატის 29 და საკონსტიტუციო სასამართლოს 328.

### როგორ ახლდება

ყოველ ღამე 01:17 UTC-ზე (თბილისით 05:17) ყველა კანონი matsne.gov.ge-ს ედრება. თუ კანონი
შეიცვალა, ახალი ტექსტი ჯერ მოწმდება (ყველა მუხლი ადგილზეა, ყოველი ხაზი სიტყვასიტყვით ემთხვევა)
და მხოლოდ ამის შემდეგ ცვლის ძველს. ყოველ ღამე 50 შემთხვევითი მუხლიც მოწმდება. ძველი რედაქციები
ინახება. სასამართლო გადაწყვეტილებები ჯერ ავტომატურად არ ახლდება: ახალი კრებულები ხელით ემატება.
დაწვრილებით: [როგორ ვაგროვებთ და ვაახლებთ მონაცემებს](docs/data.md).

### შეზღუდვები

- მხოლოდ 24 კანონი ინახება. მთავრობის დადგენილებები, ბრძანებები, მუნიციპალური აქტები,
  საერთაშორისო ხელშეკრულებები და ქალაქისა და სააპელაციო სასამართლოების გადაწყვეტილებები არ
  ინახება.
- ძიება სიტყვებით მუშაობს და არა აზრით. საუკეთესოდ ქართული სამართლებრივი ტერმინებით მუშაობს.
- ძველი თარიღისთვის სერვისი matsne-ის იმ რედაქციას აბრუნებს, რომლის თარიღიც იმ დღეს ან მანამდეა.
  ცვლილება შეიძლება მოგვიანებით ამოქმედდა.
- შენი ასისტენტი შეიძლება შეცდეს, მაშინაც კი, როცა წყარო სწორია. ყოველთვის გადაამოწმე ბმული.
- ერთ მისამართს წუთში 30 მოთხოვნა შეუძლია.

### ჩვენ იურისტები არ ვართ

ეს სერვისი მაქსიმალური სიზუსტით ავაწყვეთ, მაგრამ ჩვენ იურისტები არ ვართ და შეცდომა შეიძლება
მოგვივიდეს. **ეს არის სამართლებრივი ინფორმაცია და არა იურიდიული კონსულტაცია.** სერიოზულ საქმეზე
(სასამართლო, დაკავება, სამსახურიდან გათავისუფლება, დიდი თანხა, ბავშვები, ძალადობა) მიმართე
ადვოკატს ან უფასო იურიდიულ დახმარებას. თუ ვინმე საფრთხეშია, დარეკე **112**-ზე.

### კონფიდენციალურობა

შენს კითხვებს არ ვინახავთ. სერვერი შვიდი დღე ინახავს მხოლოდ ქსელის ჩანაწერს (მისამართი, დრო,
გვერდი, პასუხის კოდი), ბოროტად გამოყენებისგან დასაცავად. დაწვრილებით: [კონფიდენციალურობა](docs/privacy.md).

### შემოგვიერთდი

დახმარება ყველასგან მოგვესალმება. კოდის ცოდნა საჭირო არ არის: თუ მუხლი არასწორია ან ბმული არ
მუშაობს, [შეგვატყობინე](https://github.com/fuzzzy-bot/fuzzzy-law/issues/new/choose).
დაწვრილებით: [როგორ დაგვეხმარო](CONTRIBUTING.md).

კონტაქტი: support@fuzzzycore.com

---

## English

### What it is

Fuzzzy Law is a free connector that gives your AI assistant (ChatGPT, Claude, Gemini and others) the
exact text of Georgian laws. The assistant answers in the law's own words, with the official
matsne.gov.ge link and the version date. It also finds earlier wordings and published court decisions.

Free. No account. Our server never calls an AI: your assistant writes the answer, we only give it
the sources.

### Who it is for

Anyone with a question about Georgian law: dismissal, unpaid wages, child support, fines, rent,
violence. Also students, lawyers and developers who need the exact text of the law.

### Connect in 2 minutes

1. Copy the connector address: `https://law-api.fuzzzycore.com/mcp`
2. Add it to your assistant: [Claude](docs/connect/claude.md) · [ChatGPT](docs/connect/chatgpt.md) ·
   [Gemini](docs/connect/gemini.md) · [other apps](docs/connect/other-apps.md)
3. In a new chat, paste and send this text: [send this to your assistant](docs/send-this.en.md)

Then just ask, for example: "I was dismissed yesterday and no reason was given. How long do I have
to go to court?"

### What it holds

As of 21 November 2026:

- **24 laws**, 6,517 articles: the Constitution, the Civil, Criminal, Labour, Tax, administrative and
  procedure codes, and the laws on domestic violence, legal aid, patients' rights, personal data,
  social assistance, pensions and more. Full list: https://law-api.fuzzzycore.com/coverage
- **Earlier wordings** from about 2016 (earlier for some laws).
- **8,473 court decisions**: 8,116 of the Supreme Court (2004-2026, from its published collections),
  29 of its Grand Chamber and 328 of the Constitutional Court.

### How it stays current

Every night at 01:17 UTC (05:17 in Tbilisi) every law is compared with matsne.gov.ge. A changed law is
read again, checked (every article present, every line word for word) and only then replaces the old
text. Each night 50 random articles are checked as well. Earlier wordings are kept. Court decisions
are not yet updated automatically: new collections are added by hand. Details:
[how the data is collected and kept current](docs/data.md).

### Limits

- Only 24 laws are held. Government and ministerial orders, municipal acts, international treaties and
  decisions of city and appeal courts are not.
- Search matches words, not meaning. It works best with Georgian legal terms.
- For a past date the service returns the newest matsne version dated on or before that day. A change
  in it may have taken effect later.
- Your assistant can still make mistakes even when the source is right. Always open the link.
- One address can make 30 requests a minute.

### We are not lawyers

We did our best to make this accurate, but we are not lawyers and we can make mistakes. **This is
legal information, not legal advice.** For anything serious (court, detention, dismissal, large sums,
children, violence) talk to a lawyer or free legal aid. If someone is in danger, call **112**.

### Privacy

We do not store your questions. The server keeps only a network log for seven days (address, time,
path, status code) to protect against abuse. Details: [privacy](docs/privacy.md).

### Join in

Contributors are welcome, and you do not need to code: if an article is wrong or a link is broken,
[tell us](https://github.com/fuzzzy-bot/fuzzzy-law/issues/new/choose). More: [contributing](CONTRIBUTING.md).

Contact: support@fuzzzycore.com

---

## For developers

The same code runs the public service. It is two small Python projects and some text:

| Folder | What |
|---|---|
| `backend/` | The connector: an MCP server (Streamable HTTP) and a REST mirror, reading SQLite files only |
| `law_corpus/` | The data pipeline: downloads laws from matsne.gov.ge, builds and checks the stores, the daily refresh, the court collections |
| `connector/` | Generated client files (answer rules, custom GPT instructions, Claude skill, OpenAPI) and the [technical reference](connector/README.md) |
| `docs/` | Connect guides, the send-this message, data, privacy, [reliability](docs/reliability.md), [architecture](docs/architecture.md) |
| `website/` | The static website at law.fuzzzycore.com |

Run the tests (Python 3.11):

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install --no-deps -r requirements-connector.txt -r requirements-dev.txt
.venv/bin/pytest && .venv/bin/ruff check .

cd ../law_corpus
python3.11 -m venv .venv
.venv/bin/pip install --no-deps -r requirements-refresh.txt -r requirements-dev.txt
.venv/bin/pytest && .venv/bin/ruff check .
```

Build and run the connector image: see [run your own](docs/run-your-own.md). The data files are not
in the repository; that page says how to build them or point the connector at your own.

Licence: [MIT](LICENSE), © Fuzzy Core LLC. The law texts and court decisions themselves are official
documents and are not covered by copyright (Law of Georgia on Copyright and Neighbouring Rights,
Article 8); see the [data notice](docs/data.md#data-notice).
