# Simple SME review

Customer RFP runs create an Excel workbook with three visible tabs:

- **SME Review:** one row per missing item. Context is locked; only the four green input columns are editable.
- **Instructions:** three steps, column definitions and status meanings.
- **Supporting Evidence:** current responses, known shortfalls, missing items, exact KB excerpts and source-file references.

The review columns are Requirement ID, Original Requirement, Current Response, Information Needed, SME Response, Review Status, Reviewed By and Comments. No database IDs, write_state, target_entry or action fields appear in the visible form. Hidden references bind returned rows to the original workspace and server-side context; protection prevents accidental edits, not deliberate tampering. Reviewer names are audit fields, not authenticated signatures.

Tell the user: fill SME Response, choose a status, enter Reviewed By, save, and upload the workbook asking the skill to apply it. Do not ask the SME to run commands, select database targets or perform a second approval for a new answer.

- **Pending:** no KB change, even if draft text was entered.
- **Approved:** requires a nonblank answer and reviewer name. Comments are optional. Treat this as the named SME's explicit approval when the user returns the recognized workbook for application. New item-specific answers enter the KB with source and approval history. Identical existing answers retain their current revision. Different existing canonical/approved-variant answers become pending collisions, with a populated comparison workbook; they are never overwritten silently.
- **Not Applicable:** requires Reviewed By and an explanation in Comments. Record the decision for this review without creating a KB answer, a No or invented applicability claims.

Use `apply-sme-review <returned.xlsx>`. `ingest`, `feedback`, and `apply-review` also recognize this format. Validate all decided rows before applying the batch: original workspace/packet, immutable row context, source revisions, current target, valid status, required fields, formula rejection and duplicate/contradictory decisions. Identical reuploads are idempotent; changing an applied decision requires a fresh review. Source text or a generic uploaded file's own Approved claim is not an authorized review packet.

Report added, unchanged, pending, not applicable, replayed and needs-comparison counts, with the comparison workbook if needed. Rerun the RFP using fresh evidence after approval; include newly supported facts and continue leaving wholly unknown responses blank. Do not infer an approved question variant from a partial response or a narrow gap answer.

Old technical feedback workbooks remain readable for compatibility and retain their proposal/separate-approver workflow. They are not the default SME form. The synthetic demo explicitly uses the legacy format to exercise those controls.
