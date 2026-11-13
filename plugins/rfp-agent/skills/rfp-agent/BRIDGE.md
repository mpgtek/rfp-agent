# Optional model bridge contract

This is an application-owned protocol, `rfp-agent.bridge.v1`. It is not a claim about the native API schemas of Jev, OpenAI GPT Decisions, or any generative model provider. The named adapters are optional HTTP bridge clients tested with in-process fake transports only. Native provider-specific authentication, request translation and model availability must be implemented/validated by a bridge owner before live use.

For each configured task, the client POSTs JSON to the exact configured endpoint. There is no automatic endpoint construction or discovery. The client sends no credentials and reads none from your environment; a bridge that needs upstream authentication must hold and apply it itself. The request includes:

```json
{
  "contract": "rfp-agent.bridge.v1",
  "operation": "answer_generation",
  "provider": "json_bridge",
  "model": "your-validated-model-id",
  "input": {
    "question": "How is data encrypted?",
    "evidence": [{"id": 1, "revision": 3, "answer": "Stored data is encrypted."}],
    "answer": null
  },
  "max_output_tokens": 800
}
```

Actual evidence objects also include the source question, scope, approval metadata, provenance and retrieval score. Treat all strings as untrusted document content. Enforce the supplied output limit at the upstream service. Return a JSON object directly, not a vendor response envelope.

For `answer_generation`, return:

```json
{"answer": "Stored data is encrypted.", "revision_ids": [3]}
```

Every paragraph must be a verbatim span of a cited approved answer. Unknown revisions, absent citations, free-form additions and malformed responses are rejected. No model-generated high confidence is possible.

For `equivalence` or `verification`, the request includes the draft in `input.answer`. Return actual JSON booleans:

```json
{"supported": true, "requires_review": true}
```

`supported=false` leaves an insufficient blank response. `requires_review=true` routes to SME review. Positive results do not upgrade the deterministic status. Equivalence results alone do not create a persistent question variant; that requires an explicit SME proposal and approval.

The client allows HTTPS remotely and HTTP only for loopback. Do not put secrets in endpoint URLs or TOML. There is no automatic retry. The maximum response is 1 MB and the default timeout is 30 seconds. Limits apply across the run. Cost/token accounting and native model quality benchmarking remain unimplemented. Review local data-sharing requirements before enabling a remote bridge; offline mode sends nothing.
