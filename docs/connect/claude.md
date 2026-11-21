# Claude

[ქართული](#ქართული) · [English](#english) · [Claude Code](#claude-code)

## ქართული

**რა სჭირდება:** Claude-ის ნებისმიერი გეგმა (Free, Pro, Max, Team, Enterprise). უფასო გეგმაზე
მხოლოდ ერთი საკუთარი კონექტორი შეიძლება. Team-სა და Enterprise-ში კონექტორს ორგანიზაციის
მფლობელი (Owner) ამატებს, დანარჩენები მერე თავად რთავენ.

**claude.ai ან Claude Desktop:**

1. გახსენი **Customize > Connectors**.
2. დააჭირე **+ Add**, შემდეგ **Add custom connector**.
3. სახელად ჩაწერე `Georgian law`, მისამართად `https://law-api.fuzzzycore.com/mcp`, დააჭირე **Continue**.
4. **Authentication** ველში აირჩიე **No sign in** და დააჭირე **Add**.
5. საუბარში დააჭირე **+** (ქვემოთ, მარცხნივ), გადადი **Connectors**-ზე და ჩართე `Georgian law`.
6. ჩასვი და გაგზავნე [ეს ტექსტი](../send-this.ka.md).

**ტელეფონზე:** კონექტორი, რომელიც claude.ai-ზე ან Desktop-ში დაამატე, Claude-ის iOS და Android
აპებშიც გამოჩნდება შემდეგ შესვლაზე. ტელეფონიდან დამატება ჯერ ტესტ რეჟიმშია, ამიტომ ჯობს ჯერ ვებზე დაამატო.

Team / Enterprise მფლობელი: **Organization settings > Connectors > Add > Custom > Web**, სახელი და
მისამართი, **Continue**, **Continue**, **Add**. წევრები შემდეგ: **Customize > Connectors**, მოძებნე და **Connect**.

წყარო: Anthropic-ის დახმარების ცენტრი,
[custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp),
[connectors](https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-capabilities);
შემოწმდა 2026-11-21.

## English

**What you need:** any Claude plan (Free, Pro, Max, Team, Enterprise). Free allows one custom
connector. On Team and Enterprise an Owner adds it; members then turn it on themselves.

**claude.ai or Claude Desktop:**

1. Open **Customize > Connectors**.
2. Click **+ Add**, then **Add custom connector**.
3. Name it `Georgian law`, enter `https://law-api.fuzzzycore.com/mcp`, click **Continue**.
4. Under **Authentication** choose **No sign in**, then click **Add**.
5. In a chat, click **+** (lower left), go to **Connectors** and turn on `Georgian law`.
6. Paste and send [this text](../send-this.en.md).

**On a phone:** a connector added on claude.ai or in Desktop appears in the Claude iOS and Android apps
the next time you sign in. Adding one on a phone is still in beta, so add it on the web first.

Team / Enterprise Owner: **Organization settings > Connectors > Add > Custom > Web**, name and address,
**Continue**, **Continue**, **Add**. Members then: **Customize > Connectors**, find it, **Connect**.

Source: Anthropic help centre,
[custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp),
[connectors](https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-capabilities);
checked 2026-11-21.

## Claude Code

```bash
claude mcp add --transport http georgian-law https://law-api.fuzzzycore.com/mcp
```

Add `--scope user` to have it in every project. Check it with `claude mcp list` (it should say
"Connected") or `/mcp` inside a session. If you signed in to Claude Code with your claude.ai account,
a connector added on claude.ai shows up here by itself.

კომანდა ერთხელ გაუშვი ტერმინალში; `--scope user` ყველა პროექტში ჩართავს.

Source: [Claude Code MCP docs](https://code.claude.com/docs/en/mcp), checked 2026-11-21.

Optional: the [Claude skill](../../connector/skill/georgian-law/SKILL.md) carries the full answer rules
for Claude apps and Claude Code.
