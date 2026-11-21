# ChatGPT

[ქართული](#ქართული) · [English](#english) · [Codex](#codex)

## ქართული

**რა სჭირდება:** OpenAI-ის დახმარების ცენტრის მიხედვით საკუთარ MCP სერვერს ამატებენ **Pro**
(მხოლოდ კითხვის ხელსაწყოები, ჩვენი ყველა ხელსაწყო ასეთია), **Business** და **Enterprise/Edu**
გეგმები, მხოლოდ chatgpt.com-ზე (ვებში). Business-ში დამატება ადმინისტრატორს ან მფლობელს შეუძლია.
Free, Go და Plus გეგმებს ოფიციალური ინსტრუქცია არ ახსენებს, ამიტომ მათზე ვერ დაგპირდებით, რომ
იმუშავებს. ტელეფონის აპში ეს არ მუშაობს.

1. გახსენი https://chatgpt.com/plugins.
2. დააჭირე **+** ღილაკს, შემდეგ **Add custom MCP server**.
3. სახელად ჩაწერე `Georgian law`. **Connection** ნაწილში **Server URL** ველში ჩასვი
   `https://law-api.fuzzzycore.com/mcp`.
4. ავტორიზაციად აირჩიე **No authentication**.
5. წაიკითხე გაფრთხილება და დააჭირე **I understand and want to continue**, შემდეგ **Create as a plugin**.
6. დააინსტალირე შექმნილი plugin. საუბარში აკრიფე `@` და აირჩიე `Georgian law`.
7. ჩასვი და გაგზავნე [ეს ტექსტი](../send-this.ka.md).

ძველ ინსტრუქციებში (Settings > Apps > Developer mode) ეს გზა სხვანაირადაა აღწერილი; OpenAI მას ახლა
ძველ გზად მოიხსენიებს და Developer mode-ის ჩართვა აღარ სჭირდება.

წყარო: OpenAI,
[Add custom MCP server](https://developers.openai.com/api/docs/guides/developer-mode),
[Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-connectors);
შემოწმდა 2026-11-21.

## English

**What you need:** per OpenAI's help centre, custom MCP servers can be added on **Pro** (read-only
tools, which all of ours are), **Business** and **Enterprise/Edu**, on chatgpt.com (web) only. On
Business only admins and owners can add one. Free, Go and Plus are not mentioned in the official
pages, so we cannot promise they work. It does not work in the phone apps.

1. Open https://chatgpt.com/plugins.
2. Select the **+** button, then **Add custom MCP server**.
3. Name it `Georgian law`. Under **Connection**, put `https://law-api.fuzzzycore.com/mcp` in **Server URL**.
4. For authentication choose **No authentication**.
5. Read the warning, select **I understand and want to continue**, then **Create as a plugin**.
6. Install the plugin. In a chat, type `@` and pick `Georgian law`.
7. Paste and send [this text](../send-this.en.md).

Older guides describe this under Settings > Apps > Developer mode; OpenAI now calls that the legacy
route, and Developer mode no longer has to be turned on.

Source: OpenAI,
[Add custom MCP server](https://developers.openai.com/api/docs/guides/developer-mode),
[Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-connectors);
checked 2026-11-21.

A custom GPT can also use the connector through an Action with
[`connector/openapi.json`](../../connector/openapi.json) and
[`custom_gpt_instructions.txt`](../../connector/instructions/custom_gpt_instructions.txt).

## Codex

Codex (the terminal app, and Codex inside the ChatGPT desktop app) reads `~/.codex/config.toml`:

```toml
[mcp_servers.georgian-law]
url = "https://law-api.fuzzzycore.com/mcp"
```

Or run `codex mcp add georgian-law --url https://law-api.fuzzzycore.com/mcp`. Check with
`codex mcp list` or `/mcp` inside Codex. Send [this text](../send-this.en.md) at the start of a session.

Source: [Codex MCP docs](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), checked 2026-11-21.
