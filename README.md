# RFP Agent

Answer RFPs and security questionnaires from your own company knowledge base. RFP Agent imports your existing Q&A, drafts answers in your Word or Excel questionnaire using only facts it can support, leaves anything it can't support blank, and sends the gaps to your subject-matter experts (SMEs) in a simple review workbook. Free, from [MPG Technologies LLC](https://www.mpgtek.com).

## Install

**Claude Code** — run these two commands:

```
/plugin marketplace add mpgtek/rfp-agent
/plugin install rfp-agent@mpgtek-rfp-agent
```

**Codex or manual install** — download [rfp-agent-skill.zip](https://github.com/mpgtek/rfp-agent/releases/latest/download/rfp-agent-skill.zip), extract it, and move the `rfp-agent` folder into `~/.agents/skills/` (Codex) or `~/.claude/skills/` (Claude Code). See [INSTALL.md](INSTALL.md).

## Requirements

- An assistant that can run code and read files on your computer, such as Claude Code, the Claude desktop app or Codex.
- Python 3.11 or newer. On first run the skill checks its Python libraries and installs any that are missing, if package access is available.

## Use it

Start a new session and ask, for example:

1. "Build a reusable RFP knowledge base from my company documents."
2. "Answer this RFP from our KB and send missing items to SME review."
3. "Apply the approved answers in this returned SME review workbook."

The first time, it asks for your company name and source documents. After that it remembers your setup.

## Your data

Your knowledge base lives in `~/Documents/rfp-agent/rfp-kb-store` on your computer, separate from the skill. Nothing is sent to MPG. Your AI assistant processes the documents you share under its own terms. Always review answers before sending them; accuracy is not guaranteed.

## More

[Privacy](PRIVACY.md) · [Terms](TERMS.md) · [Support](https://www.mpgtek.com/#contact) · [MIT License](LICENSE) · [Developer guide](docs/DEVELOPMENT.md)
