# სხვა აპები · Other apps

ყველა ქვემოთ ჩამოთვლილი აპი ჩვენს მისამართს შესვლის გარეშე იღებს. ზოგი მხოლოდ ხელსაწყოებს
აჩვენებს და მზა მოთხოვნებს (prompts) არა; ეს არაფერს აფუჭებს. დაკავშირების შემდეგ გაგზავნე
[ეს ტექსტი](../send-this.ka.md).
Every app below accepts our address with no sign-in. Some show only the tools, not the ready-made
prompts; that is fine. After connecting, send [this text](../send-this.en.md).

Address: `https://law-api.fuzzzycore.com/mcp`. All checked 2026-11-21 against the vendor's own docs.

## VS Code (GitHub Copilot)

Run **MCP: Add Server**, choose **HTTP**, enter the address. Or in the MCP configuration file:

```json
{ "servers": { "georgian-law": { "type": "http", "url": "https://law-api.fuzzzycore.com/mcp" } } }
```

Use it in Copilot Chat in **Agent** mode. Copilot Free, Pro, Pro+ and Max can use it; on Copilot
Business and Enterprise an organisation admin must turn on the "MCP servers in Copilot" policy (off by
default). [Docs](https://code.visualstudio.com/docs/copilot/customization/mcp-servers).

## Cursor

`~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project):

```json
{ "mcpServers": { "georgian-law": { "url": "https://law-api.fuzzzycore.com/mcp" } } }
```

[Docs](https://cursor.com/docs/context/mcp).

## Mistral Le Chat

**Connectors > + Add Connector > Custom MCP Connector**, name `GeorgianLaw` (no spaces), the address,
**Connect**. Turn it on in a chat with the Tools button. Admin-only: on Free, Pro and Student the
account owner is the admin. [Docs](https://docs.mistral.ai/le-chat/knowledge-integrations/connectors/mcp-connectors).

## Perplexity

**Plugins > Add custom > Add MCP connector > Remote**, name and address; under Advanced set
Authentication **None** and Transport **Streamable HTTP**; tick the acknowledgement; **Add**. Pro, Max
and Enterprise. [Docs](https://www.perplexity.ai/help-center/en/articles/13915507-adding-custom-remote-connectors).

## LM Studio

**Program** tab > **Install > Edit mcp.json**, the same entry as Cursor. Version 0.3.17 or later.
[Docs](https://lmstudio.ai/docs/app/mcp).

## Zed

**Settings > AI > MCP Servers > Add Server > Add Remote Server**, the address.
[Docs](https://zed.dev/docs/ai/mcp).

## JetBrains AI Assistant

**Settings | Tools | AI Assistant | Model Context Protocol (MCP) > Add**, JSON as for Cursor (`url`).
[Docs](https://www.jetbrains.com/help/ai-assistant/mcp.html).

## Goose

`goose configure` > **Add Extension** > **Remote Extension (Streamable HTTP)**, the address.
[Docs](https://goose-docs.ai/docs/getting-started/using-extensions).

## Any other MCP client

The server speaks MCP over Streamable HTTP at one address, with no authentication. Test it with the
MCP Inspector:

```bash
npx @modelcontextprotocol/inspector --cli https://law-api.fuzzzycore.com/mcp --transport http --method tools/list
```

## Not possible today

- Microsoft Copilot (the consumer app): its connectors are a fixed list; custom MCP servers exist only
  in Microsoft 365 Copilot and Copilot Studio for work accounts.
- The Google AI Studio screen: not documented.
