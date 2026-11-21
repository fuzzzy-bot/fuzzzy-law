# კონფიდენციალურობა · Privacy

## ქართული

- **შენს კითხვებს არ ვინახავთ.** სერვერის ჩანაწერებში არც კითხვის ტექსტი წერია და არც შენი მისამართი.
- **ქსელის ჩანაწერი, 7 დღე.** სერვერის წინ მდგომი ვებსერვერი (nginx) იწერს მოთხოვნის მისამართს
  (IP), დროს, გვერდს კითხვის ნაწილის გარეშე და პასუხის კოდს. ის 7 დღეში იშლება. ეს გვჭირდება
  ბოროტად გამოყენებისგან დასაცავად (მაგალითად, წუთში 30 მოთხოვნის ლიმიტისთვის).
- **ჩვენი სერვერი AI-ს არ იძახებს** და შენს მონაცემებს არავის გადასცემს. პასუხს შენი ასისტენტი
  წერს; შენი საუბარი იმ კომპანიის წესებით ინახება, ვისი ასისტენტიც იყენებ (Anthropic, OpenAI,
  Google და სხვ.).
- **ვებგვერდი** law.fuzzzycore.com cookie-ებს არ იყენებს და თვალთვალის კოდს არ ტვირთავს.
- კითხვები: support@fuzzzycore.com

## English

- **We do not store your questions.** The server's logs carry neither the question text nor your address.
- **Network log, 7 days.** The web server in front (nginx) logs the caller's address (IP), the time,
  the path without the query part and the status code. It is deleted after 7 days. We need it to
  protect the service against abuse (for example the limit of 30 requests a minute).
- **Our server never calls an AI** and shares your data with no one. Your assistant writes the answer;
  your conversation is kept under the rules of the company whose assistant you use (Anthropic, OpenAI,
  Google and others).
- **The website** law.fuzzzycore.com sets no cookies and loads no trackers.
- Questions: support@fuzzzycore.com

How this is enforced in the code: the connector runs without an access log
(`backend/Dockerfile.connector`), logs errors by type only, and the nginx example
(`backend/scripts/nginx.connector.conf.example`) drops the query string; the log rotation example keeps
seven days.
