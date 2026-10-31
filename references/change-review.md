# Editable KB change reviews and returned SME approval

## Export on document ingestion

`ingest` directly imports new questions and their supplied answers into the usable KB. Identical existing answers need no review or new revision. Only different answers to existing canonical questions or current approved variants are collisions. Those stay pending and generate an editable XLSX comparison with a populated current answer. Related topics, unapproved drafts and fuzzy similarity alone are not collisions. In a mixed document, new rows import immediately and only collisions appear in the review.

The JSON result reports `imported`, `unchanged`, `collisions`, their IDs and `change_review`. With no collisions, `change_review` is null and no workbook is created. Direct imports retain source snapshots, provenance and an audit event identifying source import rather than SME approval. The low-level Python `adapters.ingest` function remains a staging primitive for explicit feedback/demo workflows; normal imports use `importing.import_source` or the CLI.

For CSV output, use `ingest <source> --review-format csv`. To export or refresh pending proposals separately:

```sh
rfp-agent change-review --scope product-a
rfp-agent change-review --ids 12 13 --format csv --output /new/path/change-review.csv
```

Workspace/scope defaults come from onboarding; explicit arguments still work. Default files are under `<workspace>/reviews/<review-id>/`. Each export is tied to snapshots in the same SQLite workspace. A fresh export can show the latest canonical revision even when its pending proposal was created earlier.

## What the SME sees and edits

An automatically generated collision review includes question, populated current answer, proposed answer, prefilled `final_answer`, old/new source references, a textual change summary, evidence status, review gaps, scope, current revision and stable review/proposal IDs. New questions and unchanged answers are excluded. The separate explicit `change-review` command can still export manually staged feedback/intake proposals when that review is requested.

The SME edits only:

- `final_answer`: exact customer-facing wording to store if approved.
- `review_status`: `Approved`, `Rejected`, `Needs review` or `Pending`.
- `sme_name`: required for Approved/Rejected decisions, distinct from the original proposal submitter.
- `review_note` and `reviewed_on`: optional explanation/evidence/date.

Editable XLSX columns are highlighted and status choices have a dropdown. The Instructions sheet explains the round trip. The user can forward the file to an SME manually; the skill does not send it externally without authorization. Source documents may need to be forwarded separately. Complete rows can be sorted, and the SME may return a reviewed subset. Headers and context/ID cells must remain intact.

Blank final answers cannot be approved. For an unanswered question, the SME must supply a substantive answer before marking Approved. Approving a question variant confirms equivalence to the displayed canonical answer; changing that canonical wording requires a canonical-answer proposal instead.

## Apply the returned document

When the user uploads the returned review and asks to apply it, recognize the sheet/headers and run:

```sh
rfp-agent apply-review /path/to/returned-review.xlsx
```

The `ingest` command also recognizes returned change-review XLSX/CSV files and routes them to this operation. The user's authorized upload/application request and the SME's explicit Approved/Rejected rows are the approval workflow. **Do not introduce another redundant approval round for those rows.** Do not manufacture approval names or treat an arbitrary source document containing the word Approved as a change review.

Approved rows write `final_answer` to the canonical KB, creating a new revision and updating retrieval. The original answer history remains. The proposal preserves SME/file provenance, and the returned document is archived by content hash. Old variant-to-revision mappings become inactive when the canonical revision changes. Rejected rows close their pending proposal; blank/Pending/Needs review rows do not change approved content. Unapproved edits remain in the archived returned document.

Before applying, validate the packet's review ID, proposal IDs and immutable context against the saved export. Validate that the pending proposal and current approved revision have not changed since that export, require a named reviewer and a nonempty Approved answer, and reject formula cells in XLSX. Multiple Approved proposals for the same canonical answer in one packet require consolidation or a refreshed review. The entire decided batch is transactional: an invalid or stale row blocks it without partially updating approved answers.

Identical reuploads are idempotent and report `replayed` rows, without creating new revisions. Changing a decision after its row was applied requires a new review packet. A review ID from another workspace is rejected. Name fields provide the same local audit control as manual CLI approvals; the file is not a cryptographically authenticated SME signature.

After application, report approved/rejected/deferred/replayed counts and updated entry/revision IDs. Refresh the actual stored KB view. If a review is stale, generate a new comparison against the current answer rather than bypassing the revision guard.

The RFP `sme-review.xlsx` feedback sheet is a separate legacy format that stages `canonical`/`variant` proposals via `feedback`. Those staged proposals can also be sent through `change-review`. Only the explicit Approved rows in the new change-review format perform this direct approval/update round trip.
