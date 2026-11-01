# RFP Agent Privacy Policy

Effective date: October 31, 2026

Publisher: MPG Technologies LLC

This policy covers RFP Agent, the free skill/plugin for building a reusable knowledge base and preparing RFP responses. The MPG website has a separate [website privacy policy](https://www.mpgtek.com/privacy).

## Information used by RFP Agent

RFP Agent reads documents and information you make available for your requested workflow. These may include company questions and answers, RFP requirements, source documents, customer or employee information contained in those documents, and SME names and comments.

The skill stores its SQLite knowledge base, source references and snapshots, answer revisions, review decisions and related working files in a local workspace outside the installed skill. Its default KB workspace is `~/Documents/rfp-agent/rfp-kb-store`. You or the hosting assistant may select another location. Generated documents and review workbooks are saved to the locations chosen for the workflow.

This information is used to retrieve evidence, draft supported answers, identify missing information and apply approved knowledge-base changes.

## What MPG receives

Nothing. The skill runs locally on your machine. The RFP knowledge base is stored in a SQLite database on your machine.

## Hosting AI service and other recipients

RFP Agent runs through a hosting assistant such as Codex, ChatGPT or Claude. The assistant may read and process the documents, questions and retrieved evidence needed for the workflow. The hosting AI provider's terms, privacy policy, account settings and retention rules apply to that processing. Local storage does not mean AI processing stays entirely on your computer.

Optional external model or decision adapters may send selected evidence to the provider you configure. Those providers have their own policies and retention rules. Export adapters for Confluence and Notion read supplied exports; they do not by themselves establish live service connections.

Initial dependency installation may contact your configured Python package index. GitHub or another distribution service may process requests when you view or download the skill, under that service's policies. These services can receive normal network request details, such as your IP address.

MPG does not control the hosting assistant, external providers, distribution services, your device backups or any cloud synchronization you enable for the workspace.

## Retention and your controls

The skill has no automatic retention-expiry schedule. Local documents, source snapshots, knowledge-base records, approval history and generated files remain until you remove them or your own storage policies remove them. Updating an answer does not erase its revision history or stored source snapshots.

You control which materials you provide and which services you configure. To remove information retained by the skill, remove the relevant local workspace and generated copies you control. Uninstalling the skill alone does not remove the separate workspace. Keep backups if you need them before deleting files.

Local deletion does not delete original source documents, other people's copies, device/cloud backups, or information retained by your hosting AI provider or optional services. Use those providers' controls or contact them for requests concerning their copies.
