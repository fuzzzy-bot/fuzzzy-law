# Send this to your assistant

After you turn on the Fuzzzy Law connector ([connect guides](connect/README.md)), paste this text into a new chat and send it. From then on the assistant answers Georgian law questions from the connector's sources.

```text
For every question about Georgian law, use the Fuzzzy Law connector and follow its instructions; if it is not available, tell me instead of answering from memory.
Answer from what it returns: quote the article word for word and give the official matsne.gov.ge link.
```

The connector itself tells the assistant how to answer when it connects; this text only makes sure the assistant uses it. It is generated from the code (`backend/app/services/connector_guidance.py`): change the code and run `python scripts/write_client_files.py`.

ქართულად: [send-this.ka.md](send-this.ka.md)
