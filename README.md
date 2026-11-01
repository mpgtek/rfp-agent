# RFP Agent

A free skill from **MPG Technologies LLC** for building a reusable company KB, drafting evidence-backed Word and Excel RFP responses, and collecting SME approvals. Your KB and source files stay in a separate local workspace; the hosting AI service processes selected content under its own policies.

## Install the skill

1. Download [rfp-agent-skill.zip](https://github.com/mpgtek/rfp-agent/releases/latest/download/rfp-agent-skill.zip).
2. Extract it and move the `rfp-agent` folder into `~/.agents/skills/` for Codex or `~/.claude/skills/` for Claude Code.
3. Start a new session and invoke RFP Agent. It checks dependencies, reuses your existing KB or guides first-time company setup, then asks for source documents.

The ZIP includes only skill instructions, runtime code, reference guides and licensing/policy files. It excludes tests, checked-in examples, synthetic scenario documents and Git history. Keep company data outside the installed folder. See [installation details](INSTALL.md).

### For developers

Clone this repository to work on the code or run tests and examples. The repository intentionally retains those development resources; regular users should install the ZIP instead. Build the installation ZIP with `python3 tools/build_skill.py`. The optional CLI demo generates its inputs from Python code and also works without the checked-in examples folder.

## Privacy, terms and support

- [Privacy Policy](PRIVACY.md)
- [Terms of Use](TERMS.md)
- [Support/contact MPG Technologies LLC](https://www.mpgtek.com/#contact). Do not include confidential documents or credentials in public issues or initial support requests.


## Review missing information

1. Open **SME Review** in the generated workbook. Each row asks for one missing item and shows the existing response for context.
2. Fill **SME Response**, choose **Approved**, and enter **Reviewed By**. Leave unfinished items **Pending**. For **Not Applicable**, enter your name and an explanation in **Comments**.
3. Save and upload the workbook, asking the skill to apply the review. Approved new facts update the KB. Conflicting existing answers receive a comparison review. Regenerate the RFP to use the approved facts.

**Instructions** explains every column. **Supporting Evidence** contains the facts already used, source excerpts and known shortfalls. Context cells are protected against accidental edits; technical references are hidden. Names are local audit fields, not authenticated signatures. See [the review rules](plugins/rfp-agent/skills/rfp-agent/references/sme-review.md).

The internal command is `apply-sme-review returned.xlsx`; `ingest`, `feedback` and `apply-review` recognize the same form. No extra proposal/approval command is needed for approved new answers. Older technical feedback workbooks keep their legacy behavior.

## Fixed single-company KB location

The default company store is **`~/Documents/rfp-agent/rfp-kb-store`**, containing `knowledge.sqlite3`, `onboarding.json`, archived sources, reviews and runs. Normal new sessions resolve this path directly, without needing a location registry. When the new folder does not exist, an existing legacy `~/Documents/Codex/rfp-agent/rfp-kb-store` is reused. Setup asks for company/scope only. Existing data is reused; access or dependency failures never justify initializing a replacement. Explicit `--workspace` and explicitly configured state registries remain available for isolated tests/alternate deployments.

The installed skill and its update ZIP do not contain the company database. Runtime/settings files remain separate from the known KB directory.

A working, offline-first Python vertical slice: source Q&A → direct import of new answers into SQLite/FTS5 → collision review for changed existing answers → customer Word/Excel responses and SME feedback → canonical revisions and question variants.

The included examples describe **MeridianDesk**, one fictional B2B case-management SaaS. The corpus has **100 distinct questions across 20 domains**, with substantive answers, explicit unsupported capabilities, plan conditions, operational limits, responsible owners and simulated internal evidence documents. They are not security assertions about any real company, and the CAIQ-like demo is not an official CSA questionnaire. The former repetitive numbered-service fixture has been replaced.

## Quick start

Python 3.11+ with SQLite FTS5 is required. Tested here with Python 3.12.14 and openpyxl 3.1.5; see `VALIDATION.md` for the actual recorded environment and results.

When invoked as an agent skill, setup is guided automatically. The agent runs `scripts/bootstrap.py`, prepares/checks its Python libraries and FTS5, asks for the company/workspace, then asks for source files. It imports new Q&A directly, reviews only conflicting replacements, and continues to RFP answering and feedback. On later invocations it resumes the saved workflow. Users do not need to run the installation commands below. See [the first-run flow](plugins/rfp-agent/skills/rfp-agent/references/first-run.md).

Before bootstrap, `python3 -S plugins/rfp-agent/skills/rfp-agent/scripts/discover_workspace.py` recovers saved company/workspace metadata without optional libraries and without creating a DB. It discovers an existing Documents/Codex/rfp-agent-runtime registry if the standard settings are absent/inaccessible; explicit `RFP_AGENT_STATE_DIR` overrides discovery. Runtime failures must not restart company onboarding. Keep the company's data folder accessible to new chats, preferably through a local project with that folder attached.

The bootstrap keeps runtime/settings outside the skill directory. It reuses a compatible current interpreter if a previous managed environment lacks libraries, or installs missing `openpyxl`/`python-docx` packages only into a managed environment. It does not install system Python or alter global packages. With no Python 3.11+/FTS5 or no package access, it reports the blocker while preserving the discovered company/KB location. `--offline` forbids downloads.

Runtime/settings defaults are `~/Library/Application Support/rfp-agent` on macOS, `$XDG_DATA_HOME/rfp-agent` (or `~/.local/share/rfp-agent`) on Linux, and `%LOCALAPPDATA%/rfp-agent` on Windows. `RFP_AGENT_STATE_DIR` or bootstrap `--state-dir` selects another permitted location. Company data remains in the separately chosen workspace.

For manual use, bootstrap prints the Python/launcher command to use:

```sh
python3 plugins/rfp-agent/skills/rfp-agent/scripts/bootstrap.py
# Using the returned Python/launcher paths:
<python> <launcher> --workspace /chosen/company-workspace setup --company "Company" --scope product-a
<python> <launcher> setup --source /path/to/company-documents
<python> <launcher> onboarding-status
```

Source selection does not itself ingest or approve answers. If no documents exist, `setup --defer-sources` starts the application-profile step. `setup` saves company, scope and sources in `<workspace>/onboarding.json`; global settings remember the active workspace. Saved defaults remove repeated workspace/scope flags from normal commands. `--workspace` and `--scope` can still override those defaults. `demo` always requires an explicit fresh workspace and never uses a saved company KB.

The following is an alternative developer installation and explicit synthetic demonstration:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ./plugins/rfp-agent/skills/rfp-agent
.venv/bin/python -m unittest discover -s tests -v

# Choose a NEW data directory outside this repository.
.venv/bin/rfp-agent --workspace ../rfp-demo-data demo
```

The demo imports 100 Q&A records, answers 30 questions, creates and ingests explicit synthetic SME feedback, verifies that pending feedback does not improve results, approves two proposals as a different actor, and processes the RFP again. It asserts that an audit-export paraphrase becomes high-confidence and that a new VPAT answer is reused while retaining compliance review. It writes `demo-result.json` with measured status counts and labeled retrieval results. No API keys or network calls are needed. Re-running `demo` requires a new workspace; normal ingestion and feedback support replay.

Coverage was informed by the public [CSA Cloud Controls Matrix/CAIQ resources](https://cloudsecurityalliance.org/research/cloud-controls-matrix) and [OWASP ASVS](https://asvs.owasp.org/). These are coverage references only: no real vendor's answers or attestations were imported. All product facts and simulated policy documents are original synthetic scenario content. `plugins/rfp-agent/skills/rfp-agent/src/rfp_agent/corpus.py` is the maintained corpus; `examples/scenario.json` is its readable export, and `examples/scenario-documents/` contains the 20 simulated evidence documents.

The 30 labeled RFP cases include 12 exact questions, seven paraphrases, five compound/near-match traps, three deliberately missing knowledge areas, and three commitment/assurance questions. For example, TLS support must not imply public mutual TLS, EU storage must not imply EU-only support personnel, and a one-hour database recovery objective must not be applied to attachments. `examples/rfp-gold.json` records expected evidence and known gaps. The gold labels are used only for demo evaluation, never to answer customer questions.

For environments where dependencies are already installed, no installation is required:

```sh
PYTHONPATH=plugins/rfp-agent/skills/rfp-agent/src python3 -m rfp_agent --workspace ../rfp-demo-data demo
```

## Normal workflow

Persistent operations use the saved company workspace after guided setup, or an explicit `--workspace` before the command. Ingestion, search and answering use the saved product/environment scope unless `--scope` overrides it. With neither setup nor an explicit workspace, the CLI requests setup. No workspace is implicitly created in the source checkout. Commands emit JSON on stdout and errors on stderr with a nonzero exit code.

```sh
rfp-agent --workspace ../my-rfp-data init
rfp-agent --workspace ../my-rfp-data ingest examples/knowledge.xlsx --scope product-a
# New Q&A is now usable. Only changed existing answers require SME review.
rfp-agent --workspace ../my-rfp-data search 'How is customer data encrypted at rest?' --scope product-a
rfp-agent detect examples/rfp.xlsx
rfp-agent --workspace ../my-rfp-data answer examples/rfp.xlsx --scope product-a
```

`answer` returns a run ID, status counts and output directory. Each run contains:

| File | Purpose |
| --- | --- |
| `input.docx` / `input.xlsx` | Original input snapshot |
| `completed.docx` / `completed.xlsx` | Preserved copy with supported drafts in the existing response column |
| `sme-review.xlsx` | All rows, evidence, routing reason, write state and editable SME fields |
| `drafts.json` | Structured drafts with evidence revision snapshots |
| `manifest.json` | Input checksum, layout, scope, status counts, task routing and usage |

The original input remains unchanged. Customer answering defaults to known answers only: exact/current approved variants, or explicit source-bound, claim-cited compositions from KB facts. Unverified keyword matches are never answers. Supported portions of compound requirements are written as partial responses, with missing items listed separately for SMEs. Wholly unsupported responses stay blank; unusable stale/conflicting facts are excluded. Review status and explanations remain in the separate SME workbook. Customer cells do not contain invented filler, missing-evidence commentary or SME-review prefixes. Related candidates may appear in review evidence but are not written as answers.

### Feedback and approval

`ingest` imports new questions and supplied answers directly into the usable KB. Identical existing answers are retained without a new revision or review. Only a different answer to an existing canonical question or current approved variant generates `kb-change-review.xlsx`, with its current answer populated. In mixed documents, new questions import immediately and only collisions go to review. Similar topics and unapproved drafts are not collisions. With no collisions, `change_review` is null and no review file is created. The JSON reports imported, unchanged and collision counts. Source-import audit events distinguish direct import from SME approval; legacy database `approved`/`approved_by` fields also represent trusted source imports.

Collision reviews are saved under the workspace's `reviews/<review-id>/` folder. They show current/proposed answers, final-answer and SME fields, sources and change metadata. Use `--review-format csv` for CSV instead.

Forward the file to an SME. They edit `final_answer`, set `review_status` to **Approved**, enter `sme_name`, and optionally add a note/date. On return:

```sh
rfp-agent apply-review /path/to/returned-change-review.xlsx
# Or upload it through ingest; this format is recognized automatically.
```

Explicit Approved rows update the KB immediately as new approved revisions; Rejected rows close proposals; Pending/Needs review rows do not change approved content. There is no additional approval round for a returned named-SME approval document that the user asks to apply. The packet is bound to its source workspace/proposal snapshots and current canonical revision. Stale/tampered context, unknown IDs, missing SME names, blank Approved answers and invalid/formula cells block the decided batch transactionally. Identical reuploads do not create duplicate revisions. Local reviewer names are audit fields, not authenticated signatures.

Generate or refresh a packet for existing pending records with `change-review --ids 101 102`, optionally `--format csv --output /new/path/review.csv`. With no IDs, it exports pending proposals for the saved/selected scope. See [the change-review reference](plugins/rfp-agent/skills/rfp-agent/references/change-review.md) for field definitions and limits.

### Older technical feedback workbooks

The following controls apply only to older technical workbooks and the synthetic demo. New customer runs use the simple review workflow at the top of this guide:

For an **older technical feedback workbook only**, in a copy of `sme-review.xlsx`, edit only `action`, `corrected_answer`, `target_entry`, `reviewer`, and `review_note`. Blank action or `skip` does nothing. Reviewer and review note are mandatory for every explicit action.

| Action | Meaning |
| --- | --- |
| `canonical` | Propose an explicit corrected/new answer. Requires `corrected_answer`. An exact question targets its canonical entry automatically. To correct a related canonical entry and add this question as a variant, select its `target_entry` from the evidence. Otherwise a new canonical question is proposed. |
| `variant` | Propose equivalence to `target_entry` from this row's evidence. A supplied correction must match the canonical answer exactly. |
| `reject` | Audit rejection of this draft; no KB change. |

```sh
rfp-agent --workspace ../my-rfp-data feedback /path/to/edited-review.xlsx
rfp-agent --workspace ../my-rfp-data proposals
# Select the returned proposal IDs after reviewing them.
rfp-agent --workspace ../my-rfp-data approve 101 102 --actor bob --reason 'Confirmed SME corrections and equivalence'
rfp-agent --workspace ../my-rfp-data history 1
rfp-agent --workspace ../my-rfp-data answer examples/rfp.xlsx --scope product-a
```

The legacy `feedback` command stages proposals rather than approving them. Its proposals can be approved manually or exported through `change-review` for the direct SME approval round trip described above. The approver must differ from the proposal submitter. Reject a pending KB proposal with `reject ID --actor NAME --reason TEXT`. Approval batches are transactional; stale canonical revisions or collisions roll back the entire batch. Replayed identical input/feedback returns its original proposal IDs. If the evidence changed since a review was generated, regenerate the review before submitting revised feedback. Updating a canonical answer invalidates earlier variant-to-revision mappings until reapproved.

Actor names provide local audit controls, not authenticated access control. Anyone with write access to the workspace can change the database. This MVP does not claim enterprise authorization, encryption at rest or tamper-evident audit logging.

## Evidence and confidence policy

| Status | Deterministic meaning |
| --- | --- |
| `high-confidence` | Exact normalized question or a human-approved variant, current approved revision, same explicit product scope, within freshness limit, no pending canonical conflict, no detected commitment language. |
| `needs-review` | Related evidence with high lexical overlap; or exact evidence requiring freshness, conflict, commitment or provider review. |
| `partial` | Some requested items have claim-cited support; those facts are written and missing items are routed to the SME. Coverage is agent-assessed; no compliance or approval is implied. |
| `insufficient` | No approved evidence in scope, or an optional verification decision rejects support. Blank response. |

FTS5 retrieves candidates, then token overlap ranks them. The lexical score is a routing heuristic, not a probability or semantic entailment test. No fuzzy match or model decision can promote a result to high confidence. Negations, numbers, and words are retained during normalization. A regex routes common contractual/compliance terms for review; it is not a comprehensive commitment detector. `--max-age-days` defaults to 365. Use distinct `--scope` values for products/environments where answers differ; there is no cross-scope fallback or inferred applicability.

Evidence includes canonical and revision IDs, source file and location, SHA-256 checksum, an archived source snapshot, approval actor/time, and the approved answer text. Every draft stores the evidence as it existed for that run. Historical canonical revisions and approval/rejection audit events persist in SQLite. FTS contains current approved canonical entries only. Variants use exact lookup against their approved revision.

Identical normalized Q&A records share source observations. Reimporting the same snapshot is idempotent. A new source with the same answer does not create a new revision or review. Distinct question wording is not automatically merged; exact canonical identity or a current approved variant establishes a collision. The Python `adapters.ingest` function is the low-level staging primitive for feedback/demo use; user-facing imports use `importing.import_source` or the CLI.

## Word answering

DOCX questionnaires with existing question/requirement and response columns are supported. Run `detect questionnaire.docx`, inspect KB evidence and use `answer questionnaire.docx` to create a same-format copy. Word table names are `Table 1`, `Table 2`, etc.; explicit column mapping uses letters with --sheet and --header-row. Nonquestionnaire tables, original text, IDs, priorities, response codes and prefilled/merged/protected/complex response cells are preserved. Only the main document XML changes; other ZIP members remain byte-for-byte identical. Paragraph-only questionnaires and complex forms are not automatically populated. See [Word and known-answer selection](plugins/rfp-agent/skills/rfp-agent/references/word-answering.md).

For a supported requirement, compose a concise answer at the requested level of detail and prepare a source-checksum/scope/revision-bound map with response text, claim citations and support/completeness/relevance/detail review. Supporting excerpts remain verbatim; the customer prose may summarize the cited facts. Run `answer questionnaire.docx --evidence-map selections.json`. The CLI checks source references, terminology/numeric anchors and basic polarity/restriction preservation; partial selections with validated item coverage write only supported claims; wholly unsupported selections stay blank. These checks do not prove semantic entailment. Per-run coverage is an explicit agent assessment, not a machine-proven semantic match or permanent approved variant. The host LLM authors and reviews the composition; it must omit irrelevant implementation details from overview answers. No network calls are needed.

Word runs contain input.docx, completed.docx, sme-review.xlsx, drafts.json and manifest.json, plus an archived evidence map when supplied. The review includes a Response locations tab with requirement IDs and table/cell references. The host can render/inspect DOCX output; the CLI does not bundle a renderer.

## XLSX detection and preservation

Headers are found in the first 40 rows on each worksheet. Supported question headers include `Question`, `Control Question`, `Consensus Assessment Question`, `Requirement`; response headers include `Answer`, `Response`, `Supplier Response`, `Vendor Response`, `Implementation Description`. Multiple candidate headers fail rather than guessing. Unrelated sheets are retained.

```sh
rfp-agent --workspace ../my-rfp-data answer customer.xlsx --scope product-a \
  --sheet Questionnaire --header-row 5 --question-column D --response-column G
```

CAIQ-like detection recognizes CAIQ labels and control IDs such as `AIS-01.1`, records the format in the manifest, and preserves control columns. This is format awareness, not complete CAIQ version/schema support. Where both Yes/No and prose columns exist, explicitly select the prose column. All cells with data validation, locked cells on protected sheets, merged cells, existing text and formulas are preserved and flagged in `write_state`. The MVP does not infer Yes/No/NA values or bypass worksheet protection.

The writer patches literal text only in selected response cells within the source ZIP archive. Other archive members remain byte-for-byte identical, including charts, formulas on other sheets, images, styles, external links and comments. Existing response-cell style attributes are retained. Formula-looking source/model text is stored as literal text. Tests verify ZIP preservation, styles, formulas, a chart fixture, merged regions and validation. This guarantee applies to parts outside the edited worksheet; it does not establish that all Excel-native objects anchored to changed cells behave correctly in every client. Only ordinary `.xlsx` with unprefixed worksheet cell XML is supported. No `.xls`, `.xlsb`, `.xlsm`, encrypted files, signed packages, prefixed worksheet XML, arbitrary namespace layouts, formula-based questions or arbitrary spreadsheet XML layouts. Excel itself has not been used for interactive validation here.

Formulas depending on response cells are preserved but not evaluated by this program. Refresh/recalculate them in the intended spreadsheet client before relying on their results.

## Source adapters

When the agent builds the KB from source material, it must first derive customer-facing answers using [the ingestion workflow in SKILL.md](plugins/rfp-agent/skills/rfp-agent/SKILL.md) and [the answer-authoring rules](plugins/rfp-agent/skills/rfp-agent/references/answer-authoring.md). Company responses and the agreed profile supply the facts; the stored answer speaks directly as the company. Source attribution, missing details and review commentary belong in metadata. Questions without substantive answers stay in the review backlog. The raw `ingest` CLI imports prepared text unchanged and does not automatically rewrite prose or remove internal commentary.

`ingest` supports a file or a recursively scanned directory of supported files. Directory import parses the entire batch before staging records and excludes symlink files. Use a directory of knowledge files, not the persistent workspace or a mixed folder containing unanswered RFPs. Empty/malformed supported files fail the batch with a clear error. Sources never execute as instructions.

| Source | Implemented boundary |
| --- | --- |
| XLSX | Explicit question/answer rows with sheet/cell provenance; same column mapping flags as `answer` |
| CSV | UTF-8 explicit Question/Answer headers and record number |
| MD/TXT | Explicit multiline `Q: ...` followed by `A: ...`; line number |
| DOCX | Tables with explicit Q&A headers, or paragraph `Q:`/`A:`, `Q1:`/`A:` and `Question 1:`/`Answer:` pairs; section names and paragraph/row provenance |
| Confluence/Notion | Normalized JSON export records with page ID, URL and upstream version; **no live API fetch/auth implementation** |
| Directory | Adapter registry by extension, atomic proposal staging |

`examples/` contains fixtures for every adapter. Generate the 100-row Excel KB, simulated evidence documents and 30-question RFP with `rfp-agent fixtures /path/to/new-fixtures`. Import `knowledge.xlsx` for the main KB; the scenario JSON, gold labels and operating-guide Markdown are scenario artifacts, not normalized adapter input. To test directory ingestion, put only the intended Q&A sources in a separate directory. Arbitrary unstructured prose is not converted to approved facts. Add a reviewed extraction stage for that use case; the `SourceAdapter` protocol and `QA` model are the extension points.

Excel source provenance retains optional category, owner, capability, evidence-document/section, document-version, review-date and evidence-kind columns. A simulated SOC 2 report is explicitly labeled simulated; the scenario does not contain a real audit report or certification.

The normalized export contract is:

```json
{
  "provider": "confluence",
  "records": [{
    "question": "Where is the policy?",
    "answer": "The fictional policy is in the handbook.",
    "page_id": "123",
    "url": "https://example.invalid/policies/123",
    "version": "7"
  }]
}
```

Replace `provider` with `notion` for Notion exports. A future live connector should fetch into this explicit record boundary and retain its native page/version provenance.

## Models and optional decisions

Customer answering uses the host LLM to compose relevant prose from known KB facts, with per-claim source references and local validation; unestablished matches are skipped. The legacy analysis/synthetic-demo path can still extract related evidence, but is not used for customer response writing. `providers.py` defines separate `Generator` and `DecisionEngine` protocols. TOML task settings independently route `answer_generation`, `equivalence`, and `verification`; see [examples/models.toml](examples/models.toml). Per-run `--config` selects task models; it cannot make unknown matches writable under the known-only policy. There are no hardcoded commercial model IDs, prices or credentials.

The optional HTTP adapters implement **our normalized bridge contract**, described in [BRIDGE.md](plugins/rfp-agent/skills/rfp-agent/BRIDGE.md). `json_bridge` supports generative evidence selection and decisions. Named `JevDecisionAdapter` and `GPTDecisionsAdapter` select optional decision bridges. They are tested with mocked transports, **not direct native Jev/GPT Decisions API connections**. You must supply and validate a bridge to the service's actual current API. No live provider has been called or benchmarked. No configured endpoint means no implied connection; external calls require an explicit endpoint, task-level `allow_network=true`, model, and a nonzero run call budget.

The optional CLI generative-provider path retains its older extractive guard: provider output must cite known revision IDs and consist of verbatim paragraphs from those approved answers. Unsupported prose is rejected and falls back to an extractive draft requiring review. This constraint applies to the optional provider bridge; the default host-agent workflow uses the claim-cited composition map described above. Decision engines may downgrade status or reject support; they cannot approve knowledge or upgrade uncertain drafts.

API failures, invalid output and budget exhaustion produce `needs-review` extractive fallbacks without printing exception details that might expose credentials. Calls have timeouts and bounded response sizes, with no automatic retries. Usage records task, provider, model and latency. Token/cost fields remain `null` rather than inventing costs; `max_external_calls` bounds requests, **not dollar spend**. No embeddings, semantic reranker, cache, automatic escalation, per-token accounting or calibrated model benchmark is implemented.

## Repository and persistent workspace

```text
rfp-agent/                 Code, tests, skill instructions, synthetic fixtures
  plugins/rfp-agent/       Shared Codex and Claude plugin
    plugin.json           Portable OpenAI manifest
    .claude-plugin/       Claude manifest
    skills/rfp-agent/     Maintained skill and runtime code
  tests/
  examples/

../my-rfp-data/             Persistent workspace, never committed with code
  knowledge.sqlite3        Approved KB, FTS5, proposals, drafts, runs, audit
  sources/                 Content-addressed source and feedback snapshots
  runs/<run-id>/           Input, same-format completed DOCX/XLSX, review, JSON evidence/manifest
```

Back up the whole workspace. Stop writers before copying the SQLite files or use SQLite's backup API; copying only the main database while WAL writes are active is unsafe. No automated retention, deletion propagation, export refresh, schema migrations beyond version 1, multi-tenant service, or distributed execution is included. Removing a source file does not retract previously approved answers. New conflicting knowledge must be explicitly imported and reviewed. Store workspaces on an access-controlled local filesystem appropriate to the source data.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests exercise the full vertical slice, four statuses, persistence, source snapshots/versioning, idempotence, approval separation, rollback on stale updates, variant collisions and invalidation, feedback tampering and stale evidence, scope isolation, layout detection, cell preservation, literal formula safety, source adapters, CLI failures and optional provider contracts. `VALIDATION.md` records the executed result and remaining limits. Synthetic improvements establish workflow correctness; they do not measure production answer accuracy.

## Semantic coverage and partial responses

Before answering, run `prepare questionnaire.docx --scope your-scope` (XLSX is also supported). The host LLM reads the requirement and scoped KB evidence, with per-topic candidates and a paged full-KB fallback. The default page includes up to 200 entries, so a small KB is fully available for semantic review despite different wording. Follow `next_kb_offset` for additional pages. This is not embedding search; source and numeric guards remain in place, and relevance/entailment are assessed by the host agent. No extra model API is called.

New evidence maps enumerate `requirements` as supported/missing, link claims to `requirement_ids` and KB excerpts, and explicitly mark coverage complete/partial/none. Partial responses must acknowledge incomplete coverage (`complete: false`, `coverage_checked: true`). Missing facts never enter the customer response. A documented negative capability is a supported fact. A known 99.7% SLA is preserved and flagged as below a requested 99.9%; service credits are not invented. See [the schema and round-trip example](plugins/rfp-agent/skills/rfp-agent/references/word-answering.md).

The default workbook has SME Review, Instructions and Supporting Evidence tabs. The SME fills the four green fields: SME Response, Review Status, Reviewed By and Comments. Approved new facts enter the KB when the recognized workbook returns for application; Pending stays open. Not Applicable needs an explanation and does not create KB content. Existing different answers go to comparison review. Hidden references and stored snapshots validate context, workspace, scope and freshness. Rerun using fresh evidence after application. Fully unknown responses stay blank.

## License

[MIT License](LICENSE). Copyright (c) 2026 MPG Technologies LLC.

## Marketplace package development

Listing metadata, icon, and skill live in [plugins/rfp-agent/](plugins/rfp-agent/). Run `python3 tools/build_marketplace.py` to package that directory directly. Claude Code users can add the repository as a marketplace with `/plugin marketplace add mpgtek/rfp-agent`, then install `rfp-agent@mpgtek-rfp-agent` after these changes are published. Both packages are written to ignored `dist/`; tests, examples, company data and local archives are excluded.
