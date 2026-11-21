# Gemini

[ქართული](#ქართული) · [English](#english) · [Gemini CLI](#gemini-cli)

## ქართული

**Gemini-ის ჩვეულებრივ აპში (gemini.google.com, ტელეფონი) საკუთარ კონექტორს დღეს ვერ დაამატებ.**
Google-ის ოფიციალური ინსტრუქცია მხოლოდ დეველოპერებისთვის განკუთვნილ სატესტო რეჟიმს აღწერს
(Gemini Apps Developer Mode). იქ მხოლოდ სისტემაში შესვლის ვარიანტებია ჩამოთვლილი; ის, რომ ჩვენი
კონექტორი, რომელიც შესვლას არ ითხოვს, იქ იმუშავებს, ოფიციალურად არ ჩანს. ვინ შეიძლება ამ რეჟიმით
სარგებლობდეს, ესეც არ წერია. როცა Google ჩვეულებრივ პარამეტრს დაამატებს, ამ გვერდს განვაახლებთ.

Gemini-ით დღეს ასე შეიძლება: **Gemini CLI** ტერმინალში (ქვემოთ), Gemini Code Assist VS Code-ში და
Gemini Android Studio-ში (ბოლო ორი მხოლოდ ხელსაწყოებს აჩვენებს, მზა მოთხოვნებს არა).

წყარო: Google, [Gemini Apps Developer Mode](https://developers.google.com/connected-apps/mcp/dev-mode/usage)
(განახლდა 2026-10-28); შემოწმდა 2026-11-21.

## English

**You cannot add your own connector in the ordinary Gemini app (gemini.google.com, phone) today.**
Google's official documentation describes only a testing mode for developers (Gemini Apps Developer
Mode). It lists sign-in options only; that our connector, which needs no sign-in, works there is not
stated, and who may use that mode is not documented. We will update this page when Google adds an
ordinary setting.

What works with Gemini today: **Gemini CLI** in a terminal (below), Gemini Code Assist in VS Code and
Gemini in Android Studio (the last two show the tools only, not the ready-made prompts).

Source: Google, [Gemini Apps Developer Mode](https://developers.google.com/connected-apps/mcp/dev-mode/usage)
(updated 2026-10-28); checked 2026-11-21.

## Gemini CLI

```bash
gemini mcp add --transport http -s user georgian-law https://law-api.fuzzzycore.com/mcp
```

or in `~/.gemini/settings.json`:

```json
{ "mcpServers": { "georgian-law": { "httpUrl": "https://law-api.fuzzzycore.com/mcp" } } }
```

(`httpUrl`, not `url`: `url` means the older SSE transport.) Check with `/mcp` in a session, then send
[this text](../send-this.en.md). Gemini Code Assist in VS Code reads the same file.

Android Studio: **Settings > Tools > AI > MCP Servers > Add via JSON**, the same JSON as above.

Sources: [Gemini CLI MCP docs](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md),
[Gemini Code Assist](https://docs.cloud.google.com/gemini/docs/codeassist/use-agentic-chat-pair-programmer),
[Android Studio](https://developer.android.com/studio/gemini/add-mcp-server); checked 2026-11-21.
