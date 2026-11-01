# Word questionnaires and known answers only

`detect input.docx` finds top-level tables with explicit question/requirement and response headers, including `Requirement` and `Vendor Response`. IDs, priorities and response codes are not answer columns. `answer` writes `completed.docx`, an unchanged `input.docx` snapshot, `sme-review.xlsx`, drafts and a run manifest under the known KB store's runs directory. XLSX answering uses the same known-answer policy and creates `completed.xlsx`.

## Select supported content

Exact canonical questions and current approved variants can reuse the stored answer when fresh and unconflicted. Merely related search hits are candidates, not answers. With no established match, the response stays blank. The host agent can compose a grounded response through the claim-cited map below; ungrounded prose is not accepted.

Inspect the requirement and sources, then compose a concise answer at the requested level of detail. Retrieval passages are evidence, not finished customer prose. Decompose compound requirements, write supported portions and ask SMEs for the missing portions. Leave a whole response blank only when no requested item has usable evidence. An existing negative capability is a valid answer. Missing knowledge must not become a No, promise, invented policy, fake URL or claim of an attached report. Do not infer S/C/R/X/3P/N or other response codes from general capability text.

Overview questions should receive overview answers. Describe the SaaS platform and the requested topology, hosting and regions. Exclude client identifiers, secrets, API keys and segregation mechanics unless those are requested. An implementation/security question can use more detail. Do not summarize every matched passage or fill a narrow response column with an operating procedure when a few supported sentences suffice.

## Semantic preparation and item coverage

Run `prepare input.docx --scope your-company-scope` (also supports XLSX). The context provides current scoped answers, their usability flags, source/revision IDs, per-topic search candidates and `next_kb_offset`. Read the whole small KB semantically, and fetch additional pages with `--kb-offset` before concluding a differently worded fact is missing. Search ranks are not answer equivalence. There is no embedding-service connection on this path.

For new maps, enumerate all requested items in `requirements`. Use `state: supported` with exact source `part_indices`; use `state: missing` with a specific `sme_question` and rationale. `coverage` is complete when all are supported, partial when some are supported, and none when all are missing. A known negative answer counts as supported, not missing. `meets_requirement: false` can flag a documented shortfall, such as 99.7% uptime versus a 99.9% target; support and compliance are different assessments.

A partial mapping includes these fields alongside its normal source, question, cell and `parts` bindings:

```json
{
  "coverage": "partial",
  "requirements": [
    {"id": "targets", "text": "RPO and RTO", "state": "supported", "part_indices": [0], "note": "Both targets are stated."},
    {"id": "backup", "text": "Backup frequency", "state": "missing", "note": "Not established by the KB.", "sme_question": "How often are backups performed?"},
    {"id": "dr-tests", "text": "Disaster recovery testing", "state": "missing", "note": "Recovery targets do not establish tests.", "sme_question": "How and how often is disaster recovery tested?"}
  ],
  "response": "Our RPO is 1 hour and our RTO is 24 hours.",
  "claims": [{"text": "Our RPO is 1 hour and our RTO is 24 hours.", "part_indices": [0], "requirement_ids": ["targets"], "supported": true, "support_note": "Preserves the exact targets."}],
  "composition_review": {"supported": true, "complete": false, "coverage_checked": true, "relevant": true, "appropriate_detail": true}
}
```

Every supported item must appear in a cited claim; claims cannot reference missing items or unrelated evidence. For `coverage: none`, include missing-item SME questions, empty `parts`, and no customer response/claims. Do not supply guessed answers, missing-evidence commentary or a generic No. The above values are illustrative and require actual supporting KB excerpts. If testing is documented, include it too and ask only for remaining gaps.

The review workbook uses [the simple SME workflow](sme-review.md): **SME Review** contains the missing-item requests; **Instructions** defines the fields; **Supporting Evidence** contains current responses, shortfalls and excerpts. SMEs edit SME Response, Review Status, Reviewed By and Comments. Approved new facts are applied when the recognized workbook is returned for application, Pending stays open, and Not Applicable requires an explanation without creating KB content. Existing different answers go to comparison review. Reuploads, immutable context, source/target freshness and batch integrity remain checked. Rerun using fresh evidence after application.

## Grounded composition

The host LLM drafts and then reviews each response for support, coverage, relevance and detail level. Each factual claim cites the zero-based indices of its supporting `parts` in the source-bound map. Keep `parts.quote` as exact current KB sentences/lines/paragraphs; the response itself can rephrase/summarize those supported facts. Add these fields to the mapping below:

```json
{
  "response": "Our platform supports SAML 2.0.",
  "claims": [{
    "text": "Our platform supports SAML 2.0.",
    "part_indices": [0],
    "supported": true,
    "support_note": "The cited source explicitly states support for this protocol; no OIDC or provisioning capability is added."
  }],
  "composition_review": {
    "supported": true,
    "complete": true,
    "relevant": true,
    "appropriate_detail": true
  }
}
```

All response text must be accounted for by cited claims. The code checks references, source terminology/numeric anchors, basic negative/future/only restrictions and required review fields. It rejects unsupported protocols/vendors/figures and arbitrary uncited prose. These conservative checks may require rephrasing; they do not prove general semantic entailment or replace the agent's claim review. Never claim the review flags are an SME approval. Complete compositions remain needs-review; incomplete compositions remain partial; no KB entries or variants are changed by answering.

Use a JSON evidence map only after this coverage assessment:

```json
{
  "format": "rfp-agent.evidence-map.v1",
  "source_sha256": "SHA256_OF_THE_ORIGINAL_RFP",
  "scope": "your-company-scope",
  "mappings": [{
    "sheet": "Table 4",
    "response_cell": "T4:R2:C5",
    "question": "Describe enterprise SAML login.",
    "coverage": "complete",
    "note": "The selected source explicitly states SAML login support; no other capability is requested.",
    "parts": [{
      "entry_id": 1,
      "revision": 1,
      "quote": "We support SAML 2.0."
    }]
  }]
}
```

IDs, text and checksum are illustrative. Obtain actual scoped entry/revision IDs and source excerpts, and actual cell identifiers from `detect`. For XLSX use its sheet and cell, e.g. RFP/E2. Unknown/duplicate cells, changed questions, mismatched scope/checksum, missing/stale revisions and fabricated source quotes are rejected. Bare yes/no fragments cannot be repurposed for a different question. Preserve conditions and negation. Without `response`, the older verbatim-join fallback still works; prefer grounded composition when raw source passages are unsuitable customer answers. Older unstructured `coverage: partial` maps stay blank. New partial maps require the item schema below and a claim-cited response; missing items never enter customer prose.

```sh
rfp-agent --workspace ~/Documents/rfp-agent/rfp-kb-store answer input.docx --scope your-company-scope --evidence-map reviewed-selections.json
```

Coverage rationale is an explicit agent assessment, not a machine-proven semantic equivalence or an authenticated SME approval. The deterministic validator enforces source identity, scope, revision freshness and literal KB text. Selections remain needs-review or partial and do not create approved variants. The map and checksum are archived with the run. Existing feedback controls govern subsequent learning.

## Preservation and limits

Only empty, ordinary response cells are changed. Merged, protected, complex/content-control and prefilled cells are preserved. Unrelated ZIP members, including styles, numbering, headers, footers, images and relationships, remain byte-for-byte unchanged. The document XML preserves question text, tables, code/priority columns and paragraph/run styles; pagination can grow as responses wrap.

Ambiguous layouts require explicit --sheet "Table N", --header-row and column letters. Paragraph-only response layouts, nested questionnaire tables, images/OCR, complex forms and signed/encrypted packages are not supported by this writer. Nonquestionnaire tables and free-form sections remain untouched. The host's document tools should render and visually inspect the output; the portable CLI does not bundle a Word renderer.
