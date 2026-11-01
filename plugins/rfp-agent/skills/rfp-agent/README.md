# RFP Agent installation

RFP Agent is a free skill from MPG Technologies LLC for evidence-backed Word and Excel RFP responses and SME review.

1. Download [rfp-agent-skill.zip](https://github.com/mpgtek/rfp-agent/releases/latest/download/rfp-agent-skill.zip).
2. Extract the ZIP. Move the extracted `rfp-agent` folder into:
   - Codex: `~/.agents/skills/`
   - Claude Code: `~/.claude/skills/`
3. Start a new session and invoke RFP Agent. It checks dependencies, reuses your existing KB or guides company setup, then asks for source documents.

The installed folder must contain `SKILL.md` directly, without an extra nested `rfp-agent` folder. Updates replace the installed skill files; keep your data outside that folder.

Python 3.11+, SQLite FTS5, openpyxl, python-docx and lxml are required. Setup checks these and can install missing Python libraries into a separate managed environment when package access is available.

The default company KB is `~/Documents/rfp-agent/rfp-kb-store/knowledge.sqlite3`. No company data is included in the download. The hosting AI service processes selected content under its own settings and policies.

## Package contents

This download contains skill instructions, runtime code, reference guides and licensing/policy files. Tests, checked-in examples and synthetic scenario documents stay in the [development repository](https://github.com/mpgtek/rfp-agent).

The optional `fixtures` and `demo` commands generate their synthetic inputs from bundled Python code; they do not require the repository's examples folder. Demo runs always require a fresh, explicitly selected workspace outside the installed skill. Never import synthetic data into your company KB.

See the [full documentation](https://github.com/mpgtek/rfp-agent#readme) for developer installation, source formats, optional provider configuration and limitations. The normalized bridge contract is also included in [BRIDGE.md](BRIDGE.md).

[Privacy](PRIVACY.md) · [Terms](TERMS.md) · [MIT License](LICENSE)

Support: [MPG Technologies LLC](https://www.mpgtek.com/#contact). Do not send credentials or confidential documents in public issues or initial support requests.

On Windows, `~` denotes your user profile (for example, `C:\Users\your-name`); use `py -3` in place of `python3` in command examples. Existing installations continue to use the legacy `~/Documents/Codex/rfp-agent/rfp-kb-store` if the new location does not exist.
