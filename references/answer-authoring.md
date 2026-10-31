# Deriving customer-facing KB answers

**Apply during KB construction, before the prepared Q&A is stored.** This rule applies to source-derived answers from every supported source adapter, including spreadsheets, documents, text, directories and normalized Confluence/Notion exports. Archive the raw input separately; import the prepared customer-facing answers. Do not postpone this step until an RFP response is generated.

The stored `answer` is reusable customer-facing content. Preserve already-answered Q&A as supplied unless rewriting is requested. When deriving answers from narrative material, write as the company speaking about its own system. Treat supplied company responses and the agreed application profile as the source of truth. New source Q&A becomes usable on import; only conflicting replacements of existing answers require SME approval.

Keep source attribution, citations/excerpts, source hashes, evidence quality, unanswered subparts, reviewer comments, contradictions and follow-up requests in provenance or review metadata. Do not append process commentary such as “according to the supplied notes,” “the source does not specify,” “not yet documented,” “not confirmed” or “the prior design proposes” to the customer answer.

Answer the supported scope directly. If a session description only establishes an encrypted cookie without PII, say that; do not invent identifier generation details or insert a disclaimer about the missing algorithm. If Okta is the stated 2FA integration, name Okta; do not invent push, FIDO or biometric factors. Track narrower unanswered subparts separately.

Preserve actual negative capabilities, scope/plan boundaries, future versus current functionality, internal objectives versus contractual guarantees, and controls versus completed test results. Confident prose must not change the meaning of a source claim. A source-backed “No” is a valid answer. An unknown capability is not automatically “No.”

When no substantive answer is supported, leave the customer-answer field blank and track the question and SME follow-up separately. Do not fill it with uncertainty prose or invented capabilities. The explicit Q&A ingestion CLI expects nonempty Q&A; unanswered intake items should remain a separate review backlog or explicit pending intake record until an answer is supplied.

## Illustrative wording only

Examples below show writing style; they are not facts for a user's KB. Use the actual supplied evidence and retain its limits.

- If the source states an encrypted cookie contains no PII, write that directly without inventing session-ID generation details.
- If the source gives a vulnerability-scan frequency, preserve that exact frequency.
- If authentication is limited to one protocol or identity provider, preserve that limit and request SME input for other requested protocols.

Retain the raw imported material and any editorial audit. Wording cleanup does not create an SME approval or resolve a separate evidence gap.

## Ingestion check

Inspect actual stored canonical answers and any collision proposals after import. Confirm answer fields match the supplied/prepared customer-facing text, internal commentary remains in metadata and unanswered items remain in the backlog. Record new entries as source imports without inventing SME approvals. Only collision proposals produce an automatic change review.
