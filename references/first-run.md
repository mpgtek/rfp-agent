# First invocation and guided onboarding

Use this flow when the user invokes the skill to do RFP/KB work. A question about the skill's design or capabilities does not itself trigger installation or onboarding. Do not require users to run setup commands themselves.

## Step 1 — recover saved state, then prepare the runtime

Run `python3 -S scripts/discover_workspace.py` first. Normal discovery directly checks `~/Documents/Codex/rfp-agent/rfp-kb-store`, independent of the location registry or optional Python libraries. It does not create a DB. Reuse the company and scope in that folder's onboarding.json. Runtime/settings locations remain separate; explicit state/workspace selections support isolated tests. Never select a per-chat store.

If discovery reports an access error or missing saved DB, restore folder access or locate the existing workspace; do not rerun company onboarding or initialize an empty replacement. `--workspace /existing/company-folder` can recover metadata when its registry was moved. A local project with the company workspace attached gives new chats access to that folder. Local data still requires an eligible session with local access.

From the installed skill root, run:

```sh
python3 scripts/bootstrap.py
```

The bootstrap prepares a managed environment outside the skill directory and verifies imports and FTS5. If an existing environment is incomplete but the Python running bootstrap already has compatible dependencies, it reuses that interpreter without downloading packages or changing global libraries. If necessary, obtain the host-provided dependency runtime and rerun bootstrap with it before attempting installation. Remaining missing libraries are installed only into the managed environment. It outputs JSON with `run_command`, runtime mode/paths, onboarding state and next step. Use those returned paths; do not assume a globally installed command.

A runtime failure does not mean the KB is absent. Preserve the company/workspace found by discovery, report the dependency failure and avoid repeated first-time prompts.

Run the check on later invocations too. A healthy runtime is reused without dependency downloads. Use an explicit `--state-dir` only when the host/user needs a different permitted runtime location. That location must be outside the skill. The generated launcher remembers it. `--offline` forbids package downloads and reports missing dependencies.

Proceed automatically within the invoked task. If the host enforces a permission boundary or network/package access is unavailable, explain the specific blocker and use an available supported runtime or permitted location where possible. Do not disable security controls or claim setup succeeded after failure. Python 3.11+ with FTS5 must exist on the host; the bootstrap does not install a system Python or modify the global Python environment.

## Step 2 — confirm the company only on first use

If setup is absent, ask for the company/product and scope only. The KB folder is already fixed at `~/Documents/Codex/rfp-agent/rfp-kb-store`; do not ask the user to choose a location. Reuse company details already supplied. Do not use a demo company or silently create a populated sample KB.

Example: “Which company/product is this for? I will keep its KB in the fixed rfp-kb-store folder.”

After the company is known, run the returned launcher with:

```text
--workspace ~/Documents/Codex/rfp-agent/rfp-kb-store setup --company <name> --scope <product-environment>
```

This creates an empty SQLite workspace, `inputs/`, source archive, reviews and run folders, then saves the company/scope/workspace selection. Existing compatible workspaces can be registered without resetting data. A different company requires a separate workspace. Do not recreate a missing saved database silently.

## Step 3 — ask for source material

Ask for existing Q&A files, prior RFPs, architecture/security documents or a source directory. Use the host's normal attachment flow or ordinary chat for file requests; text-only question tools can collect paths and preferences. Do not ask for API keys or paid model configuration to complete the offline default workflow.

Register source paths through:

```text
setup --source <path-1> --source <path-2>
```

The saved workspace is reused automatically. Registration selects inputs; it does not ingest or approve them. User attachments may be copied to the workspace's `inputs/` directory while retaining the original provenance. Do not point ingestion at the managed workspace or its archived sources/runs.

If the user has no documents, use `setup --defer-sources` and guide them through an application profile first. Start with product functions and hosting, then security/data handling, then BCDR/operating commitments. Draft the profile for review and retain unknowns. Do not invent company facts or fill the KB with a synthetic example unless explicitly requested.

## Step 4 — derive, import and show actual stored Q&A

Follow the required ingestion and answer-authoring rules in SKILL.md. Narrative sources require the agent's extraction/authoring step before the deterministic CLI import. Write confident customer-facing answers from the supplied company facts; store gaps and attribution separately. Keep unanswered questions in the SME backlog rather than supplying invented or uncertainty-filled answers.

Import supported Q&A using the saved company scope. Already-answered source documents retain their supplied wording. New questions become usable canonical Q&A immediately; unchanged answers need no review. Only a different answer to an existing canonical question/current approved variant generates a collision review, with its current answer populated. Provide that workbook for SME review only when collisions exist. Report imported, unchanged and collision counts; no collision means no review file. A readable HTML view may show actual stored data. Keep gaps in metadata and unanswered items in the backlog.

## Step 5 — resolve collisions when present

Skip this step when there are no collisions. Importing supplied new Q&A needs no extra approval. For an existing answer being replaced, show the concrete current/proposed comparison and use the authorized review workflow. No sample approvals or invented reviewers. Unresolved questions remain in the backlog; users may proceed with usable imported knowledge.

When the user uploads a returned change review for application, its named-SME Approved rows supply that approval step. Run `apply-review` without another approval round; apply the final wording, preserve history and leave other rows pending. Follow [change-review guidance](change-review.md) for validation, stale review handling and safe reuploads.

## Step 6 — process an RFP

When usable knowledge is available, accept DOCX or XLSX RFPs. Follow [Word and grounded-answer guidance](word-answering.md), detect existing response columns and inspect KB evidence. Compose a concise response at the requested level of detail; cite each claim to current source excerpts and check support, completeness and relevance. Keep raw passages and implementation details out of overview answers. Run prepare and assess each requested item semantically across scoped KB evidence. Write supported portions, route missing items through the plain-language SME Review form, and leave wholly unsupported responses blank. Run answering in the fixed workspace/scope and provide the same-format copy, filled/skipped counts and separate SME Review workbook with instructions and evidence. Preserve the original; render/inspect Word output when host tools are available.

## Step 7 — learn and resume

Ingest explicit SME feedback as pending changes, obtain authorized approvals and reuse approved corrections/variants on the next RFP. At the start of subsequent invocations, call `onboarding-status` and resume at its `next_step`. Do not repeat company, folder or source-selection prompts unnecessarily. New sources or changed scope may need a focused follow-up question.

The guided flow is conducted by the agent in conversation. The CLI exposes persistent setup/state and the next prompt; it does not open its own chat UI. Users can also operate the same commands directly if they prefer.
