# RFP Agent

RFP Agent helps proposal, sales engineering and security teams build a reusable company knowledge base and draft evidence-backed answers to Word and Excel RFPs and security questionnaires. It imports your supplied question-and-answer documents with source references and revision history, composes concise answers from supported knowledge-base facts, leaves unsupported questions blank, and collects the remaining items in a simple SME review workbook. Named-SME approvals are applied back to the knowledge base, and conflicting existing answers are shown side by side for comparison before anything changes.

## Requirements

Use an assistant that can run code and read files on your computer, such as Claude Code, the Claude desktop app or Codex, with Python 3.11 or newer. A chat session without local code and file access cannot read or save your knowledge base.

## What it runs and where data goes

- The skill runs Python code locally on your machine: Python 3.11 or newer, SQLite FTS5, openpyxl, python-docx and lxml. On first use its setup script checks these libraries and, if any are missing and package access is available, installs them from your configured Python package index into a separate managed environment outside the plugin folder.
- Your knowledge base, source snapshots and review history are stored outside the plugin, and no company data is bundled.
- The plugin sends nothing to MPG Technologies LLC. Your assistant processes the documents and evidence you share in the conversation under its own terms and settings. Optional external model adapters send selected evidence only to a provider you configure yourself. There is no hosted database and no live Confluence or Notion connection; those adapters read normalized exports you supply.

Answers require human review, and factual accuracy is not guaranteed.

## Usage

Ask your assistant, for example:

- "Build a reusable RFP knowledge base from my company documents."
- "Answer this RFP from our KB and send missing items to SME review."
- "Apply the approved answers in this returned SME review workbook."

See [PRIVACY.md](PRIVACY.md), [TERMS.md](TERMS.md) and the [MIT License](LICENSE). Source and full documentation: [github.com/mpgtek/rfp-agent](https://github.com/mpgtek/rfp-agent). Support: [mpgtek.com](https://www.mpgtek.com/#contact).
