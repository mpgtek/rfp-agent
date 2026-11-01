"""Authored scenario, not company claims or copied third-party questionnaire answers.

One fictional product: MeridianDesk, a multitenant B2B case-management SaaS.
Public frameworks guide coverage only; all product facts below are invented.
"""
REFERENCE_URLS = [
    "https://cloudsecurityalliance.org/research/cloud-controls-matrix",
    "https://asvs.owasp.org/",
]

# Category, responsible role, five distinct requirements with substantive answers.
GROUPS = [
    ("Governance", "Security lead", [
        ("Who is accountable for the information security program?", "The Security Lead owns the program and reports risk decisions to the COO monthly. Engineering owns remediation delivery; Product cannot waive a high-risk finding without Security Lead approval.", "supported"),
        ("How often are security policies reviewed?", "Policy owners review the security policy set annually and after a material architecture or regulatory change. The policy register records the owner, revision date and approval decision.", "supported"),
        ("How are security exceptions approved and tracked?", "Exceptions require a named business owner, compensating controls and a Security Lead approval. They expire after at most 90 days; renewal requires a fresh risk assessment.", "supported"),
        ("How is the risk register maintained?", "Security and service owners assess risks quarterly using likelihood and impact ratings. High risks receive a remediation owner and target date, and overdue items are escalated to the COO.", "supported"),
        ("What customer responsibilities apply to MeridianDesk?", "Customers administer their users, configure identity-provider policies, classify uploaded information and review tenant permissions. MeridianDesk operates the application, underlying infrastructure and backups; customers remain responsible for their own exports.", "shared responsibility"),
    ]),
    ("Assurance", "GRC manager", [
        ("Is a SOC 2 Type II report available?", "In this fictional scenario, a SOC 2 Type II report covering Security and Availability for January through June 2026 is available under NDA. It covers the production SaaS service, not customer-managed integrations or beta features. This is a simulated report, not an actual attestation.", "conditional"),
        ("Is MeridianDesk ISO 27001 certified?", "No. The fictional company has not obtained ISO 27001 certification. An internal gap assessment exists, but neither that assessment nor a sales proposal should be represented as a certificate.", "not supported"),
        ("What independent penetration testing is performed?", "An external assessor tests the web application and public API annually and after a major authentication redesign. Customers can request a redacted executive summary and remediation status under NDA; raw exploit details are restricted.", "conditional"),
        ("May customers store payment card data in the product?", "No. Payment card numbers and card verification codes are prohibited in case records and attachments. Subscription payments are collected by an external payment processor through its hosted payment page; MeridianDesk does not offer a PCI card-data environment.", "not supported"),
        ("Will MeridianDesk sign a HIPAA business associate agreement?", "No. MeridianDesk does not offer a business associate agreement and is not intended for protected health information. Customers requiring that agreement must select another service rather than treating standard privacy terms as a substitute.", "not supported"),
    ]),
    ("Identity", "Identity engineer", [
        ("Which single sign-on protocols are supported?", "Enterprise tenants can use SAML 2.0 or OpenID Connect with one customer identity provider. Starter tenants use email-based accounts. Identity-provider initiated SAML is supported; multiple simultaneous identity providers per tenant are not.", "conditional"),
        ("How is multi-factor authentication enforced?", "Workforce access requires phishing-resistant security keys. Enterprise customer tenants enforce MFA through their identity provider. Local customer accounts can enable authenticator-app MFA, but tenant-wide mandatory local MFA is not available on Starter.", "conditional"),
        ("What is the password policy for local accounts?", "Local passwords must have at least 14 characters and are checked against a breached-password denylist. Passwords are salted and hashed with Argon2id; arbitrary periodic password rotation is not required unless compromise is suspected.", "supported"),
        ("How are users provisioned and deprovisioned?", "Enterprise tenants can create, update and disable users using SCIM 2.0. Disabling a user revokes active application sessions within 15 minutes. Starter tenants manage users manually; disabling an identity-provider account alone does not remove historical audit records.", "conditional"),
        ("What session timeout controls are available?", "Interactive sessions expire after 30 minutes of inactivity and have a 12-hour absolute lifetime. Enterprise administrators may shorten the inactivity timeout to 15 minutes. API tokens follow their own expiry settings and do not inherit browser session timeouts.", "supported"),
    ]),
    ("Authorization", "Application security engineer", [
        ("How does role-based access control work?", "The built-in tenant roles are Owner, Administrator, Agent and Read-only Auditor. The application checks tenant membership and resource permissions on each server-side request. Only Owners can change billing contacts or delete the tenant.", "supported"),
        ("Can customers define custom permission roles?", "Enterprise tenants may create up to 20 custom roles by combining published permissions. Field-level permissions and arbitrary scripting of authorization rules are not available. Starter tenants use built-in roles only.", "conditional"),
        ("How is employee access to production approved?", "Engineers request temporary production access through the access workflow with a ticket reference and manager approval. Privileged grants expire after four hours, require workforce MFA and are recorded in the administrative audit log.", "supported"),
        ("How frequently are privileged access rights reviewed?", "Security reviews production administrator access every quarter and on role changes. Tenant administrators receive a downloadable user-and-role inventory, but customer access reviews are the tenant owner's responsibility.", "shared responsibility"),
        ("How are service accounts and API tokens restricted?", "Each API token belongs to a tenant service account and has explicit read/write scopes. Tokens are displayed only at creation, may expire in 1 to 90 days, and can be revoked immediately. Shared employee credentials are prohibited.", "supported"),
    ]),
    ("Cryptography", "Platform security engineer", [
        ("How is customer data encrypted at rest?", "Production database volumes, object storage and backups use AES-256 encryption with cloud KMS-managed keys. This protects stored media; authorized application processes can still decrypt data to serve customer requests. It is not end-to-end encryption.", "supported"),
        ("Which transport encryption versions are accepted?", "Public web and API endpoints accept TLS 1.2 and TLS 1.3. TLS 1.0 and 1.1 are disabled. HTTP requests redirect to HTTPS, and production web responses include HSTS.", "supported"),
        ("Are customer-managed encryption keys supported?", "No. MeridianDesk currently supports provider-managed KMS keys only. Bring-your-own-key, hold-your-own-key and customer-triggered cryptographic erasure are not available. Customers cannot upload their own KMS key to an Enterprise tenant.", "not supported"),
        ("Where is mutual TLS used?", "Mutual TLS authenticates selected internal service-to-service connections in the production cluster. Public API clients authenticate with scoped bearer tokens; client-certificate authentication at the public API edge is not supported.", "conditional"),
        ("How are encryption keys and application secrets rotated?", "KMS master keys use annual automatic rotation. Database credentials are rotated at least every 90 days and after suspected exposure. Application secrets are retrieved from a secrets manager, not stored in source code or build images.", "supported"),
    ]),
    ("Privacy and residency", "Privacy lead", [
        ("In which regions can customer content be hosted?", "At tenant creation, customers select either the US region in Virginia or the EU region in Frankfurt. Case records, attachments, search indexes and backups stay in the selected region. The service does not offer a Singapore or Australia hosting region.", "conditional"),
        ("Can an existing tenant change its hosting region?", "A region change requires a support-led migration to a new tenant and a planned cutover. There is no in-place region toggle. The migration requires approval of the new region, export/import validation and deletion scheduling for the original tenant.", "conditional"),
        ("Can support personnel access EU tenant content from outside the EU?", "Yes, in limited circumstances. Approved support staff may access tenant content through audited, time-limited sessions from the US or EU. Selecting EU storage does not promise EU-only personnel access; customers must review the documented transfer safeguards.", "conditional"),
        ("Is a data processing addendum available?", "A standard data processing addendum is available for enterprise review. It describes processor obligations, subprocessors and international transfer terms. Customer-specific changes require privacy and legal review; sales staff cannot approve modified clauses.", "conditional"),
        ("How are data subject requests handled?", "The customer acts as controller and authenticates the requestor. MeridianDesk provides export and deletion tools for customer administrators, and Privacy can assist through a verified support case. Legal preservation requirements can limit deletion of specific records.", "shared responsibility"),
    ]),
    ("Retention and disposal", "Data operations lead", [
        ("How long are deleted case records retained before purge?", "Deleted case records remain recoverable in a tenant recycle bin for 30 days, then are purged from active databases during a daily job. The retention period is fixed in the current product; backups can retain prior copies for up to 35 additional days.", "supported"),
        ("What is the backup retention period?", "Encrypted daily backups are retained for 35 days in the tenant's selected region. They are used for disaster recovery and cannot be searched or selectively edited as a customer archive. Expired backup objects are removed through storage lifecycle rules.", "supported"),
        ("What happens to customer data after subscription termination?", "An authorized tenant owner can export data during a 30-day retrieval window after termination. Active content is then scheduled for deletion; backup copies age out within the normal 35-day backup cycle. Legal holds are handled separately by Legal.", "conditional"),
        ("Can customers configure a legal hold on individual cases?", "No native per-case legal hold exists. Customers with preservation obligations should export records into their own controlled archive before normal deletion occurs. A support request is not a substitute for a formal preservation arrangement.", "not supported"),
        ("How are storage media disposed of?", "Cloud infrastructure providers handle physical media retirement under their documented disposal controls. MeridianDesk removes logical objects and destroys obsolete access paths; it does not physically handle disks or provide a customer-specific disk destruction certificate.", "shared responsibility"),
    ]),
    ("Infrastructure and isolation", "Platform lead", [
        ("How are customer tenants isolated?", "The service uses a shared application tier and shared regional database clusters. Every customer record carries a tenant identifier, and authorization checks constrain queries to that tenant. Enterprise plans do not include a dedicated database or dedicated compute cluster.", "supported"),
        ("Are production and nonproduction environments separated?", "Production and staging run in separate cloud accounts with separate identities, networks and secrets. Production customer data is not copied into developer environments; test fixtures are generated or irreversibly anonymized before use.", "supported"),
        ("Is database infrastructure directly reachable from the internet?", "No. Production databases use private network addresses and accept connections only from approved application and maintenance paths. Administrators use an audited access gateway; opening a public database endpoint is prohibited by deployment policy.", "supported"),
        ("What protections exist against denial-of-service attacks?", "The public edge uses managed DDoS filtering, a web application firewall and request throttling. Platform staff monitor saturation and can temporarily restrict abusive traffic. These measures reduce exposure but do not promise uninterrupted service under every attack.", "supported"),
        ("Can the product run in a customer's own cloud account?", "No. MeridianDesk is delivered as an operated multitenant SaaS. On-premises deployment, customer-managed Kubernetes and deployment into a customer's cloud subscription are not supported.", "not supported"),
    ]),
    ("Secure development", "Engineering manager", [
        ("What review is required before code reaches production?", "Production changes require a pull request, automated test checks and review by an engineer other than the author. Branch protection blocks direct pushes to the release branch. Emergency changes are reviewed retrospectively within one business day.", "supported"),
        ("How is security incorporated into software design?", "New authentication flows, sensitive-data handling and cross-tenant features require a threat model during design review. Security records identified trust boundaries and abuse cases, and tracks mitigation work before the feature can be enabled broadly.", "supported"),
        ("What automated application security testing runs in the build?", "The build runs static analysis, secret detection and dependency scanning on pull requests. High-severity confirmed issues block release unless an approved, time-limited exception exists. Scanner output alone is not treated as proof that the application is vulnerability-free.", "supported"),
        ("How are third-party software dependencies controlled?", "Dependencies are pinned through reviewed lockfiles and scanned on every build and daily against updated advisories. The build produces an internal software bill of materials. External distribution of the full SBOM requires a security review because it contains implementation detail.", "conditional"),
        ("How are releases rolled back?", "Application releases use staged rollout with health checks and a retained previous container image. Operators can roll back application code within minutes. Database migrations must remain backward-compatible during rollout; destructive migrations require a separate recovery plan.", "supported"),
    ]),
    ("Vulnerability management", "Security operations lead", [
        ("What are the remediation targets for vulnerabilities?", "Confirmed critical vulnerabilities have a 72-hour remediation target and high findings have a 14-day target. Medium and low findings target 60 and 120 days respectively. These are internal operating targets; any exception needs documented risk acceptance.", "supported"),
        ("How frequently are infrastructure vulnerabilities scanned?", "Container images are scanned at build and daily in the registry. Managed-host and cloud configuration checks run at least daily. Internet-exposed assets receive a weekly authenticated scan where supported and additional scanning after significant changes.", "supported"),
        ("How can researchers report a security vulnerability?", "Researchers can use the published security-report form at the fictional example.invalid security portal. Reports enter the security triage queue and receive an initial response within two business days. There is no paid public bug-bounty program in this scenario.", "supported"),
        ("How are unsupported operating systems and runtimes handled?", "Platform inventories operating-system images and runtime versions monthly. End-of-support components must be upgraded or covered by an approved short-lived exception with compensating controls. Production containers are rebuilt from maintained base images.", "supported"),
        ("How are newly disclosed critical vulnerabilities triaged?", "Security determines exposure using the component inventory and running image versions, then opens an incident or expedited patch ticket as appropriate. Internet exposure, exploit availability and privilege impact influence priority; a scanner severity number alone does not determine closure.", "supported"),
    ]),
    ("Audit and monitoring", "Detection engineer", [
        ("Which customer actions are recorded in the tenant audit log?", "The tenant audit log records sign-ins, user and role changes, API token creation or revocation, exports and case deletions. Each event includes a UTC timestamp, tenant, actor, event type and source address when available. Case message bodies and attachment contents are excluded.", "supported"),
        ("How long can customers access audit events?", "Enterprise tenants can query 365 days of audit events; Starter tenants can query 30 days. Customers needing longer retention must export events to their own archive before that window expires. Audit-event retention is separate from deleted case retention.", "conditional"),
        ("Can tenant administrators alter or delete individual audit events?", "No. Tenant administrators have read/export access only. Events are written to append-only storage through the audit service, and production operators cannot alter events through the application. Administrative access to the backing storage is separately restricted and logged.", "supported"),
        ("How can administrators export tenant audit events?", "Enterprise administrators can export audit events as paginated JSON through the Audit Events API or download CSV in the console. The API supports timestamp filters and cursor pagination. There is no native push connector to a customer SIEM; customers operate their own collector.", "conditional"),
        ("How are suspicious production activities detected?", "Security alerts cover repeated authentication failures, unusual privileged access, bulk exports and unexpected cloud configuration changes. An on-call responder triages high-priority alerts continuously. Customers do not receive raw internal detection rules or direct access to the production SIEM.", "supported"),
    ]),
    ("Incident response", "Incident commander", [
        ("Is there a documented incident response process?", "The response process covers triage, containment, evidence preservation, recovery and post-incident review. An incident commander coordinates Security, Engineering and Customer Support, with Legal and Privacy engaged when the incident affects personal information.", "supported"),
        ("When are customers notified of a confirmed data breach?", "The standard data processing terms require notice without undue delay after confirmation of a breach affecting that customer's personal data, with an initial target of 48 hours after confirmation. This is not a promise to report every unverified alert or to accept a customer's proposed one-hour deadline.", "conditional"),
        ("How often is the incident response plan exercised?", "Security runs a cross-functional tabletop exercise twice per year, including one customer-data exposure scenario. The exercise records response gaps, accountable owners and due dates. Exercise completion is tracked separately from recovery testing.", "supported"),
        ("How are customers informed during a service incident?", "The public status page provides incident updates and tenants can subscribe to email notifications. For confirmed tenant-specific security incidents, Support contacts the registered security contact through an authenticated case; sensitive details are not published on the public page.", "supported"),
        ("What post-incident information is shared with affected customers?", "For a material outage or confirmed customer-data incident, MeridianDesk prepares a written summary describing impact, timeline, contributing causes and corrective actions. Distribution may be limited to affected customers, and details that expose another tenant or an active investigation are redacted.", "conditional"),
    ]),
    ("Continuity and recovery", "Reliability engineer", [
        ("How does the application tolerate an availability-zone failure?", "Production application workers run across two availability zones in the selected region behind managed load balancing. The regional database uses a multi-zone standby. This design tolerates a zone failure but does not provide automatic cross-region failover.", "supported"),
        ("What is the disaster recovery time objective?", "The documented recovery time objective is eight hours for a regional service recovery from backups. It is an internal recovery objective measured in exercises, not a customer-specific guaranteed restoration deadline. Customer integration recovery remains the customer's responsibility.", "conditional"),
        ("What is the disaster recovery point objective?", "The recovery point objective is one hour for production case records, using continuous database log shipping and tested restore procedures. Attachment recovery can lag by up to four hours. The one-hour objective must not be represented as zero data loss or applied to every data type.", "conditional"),
        ("How often are backup restores tested?", "Reliability performs a sample database and attachment restore every quarter and a full regional recovery exercise annually. Tests check record integrity, application startup and access restrictions. Failed checks produce tracked remediation work before the exercise is closed.", "supported"),
        ("Are backups replicated outside the customer's selected region?", "No. Backup copies remain in a separate cloud account in the selected region. A total regional loss can therefore affect both production and recovery availability; the standard deployment does not provide geographic backup replication.", "not supported"),
    ]),
    ("Workforce and endpoints", "People operations manager", [
        ("What background screening applies to employees?", "Background screening is performed before workforce access is granted where permitted by local law. The scope depends on role and jurisdiction. A delayed or legally prohibited check requires People Operations and Security to agree on access restrictions.", "conditional"),
        ("What security training do employees receive?", "Employees complete security and privacy training during onboarding and annually thereafter. Engineers also complete secure-development training. Completion is tracked, and overdue training can result in suspension of privileged access until it is completed.", "supported"),
        ("How are employee devices secured?", "Workforce laptops are centrally managed, use full-disk encryption and endpoint detection, and lock after at most ten minutes of inactivity. Devices with disabled management or overdue critical updates are blocked from the workforce access gateway.", "supported"),
        ("Are personal devices allowed to administer production?", "No. Production administrative access requires a managed corporate laptop with a valid device posture check. Personal phones may be used as an MFA factor, but that does not authorize production access from a personal computer.", "not supported"),
        ("How quickly is access removed when an employee leaves?", "People Operations schedules account disablement for the employee's effective departure time. Identity, access-gateway and source-control access are revoked through the offboarding workflow, with completion checked by Security. Involuntary departures are coordinated before notice is delivered.", "supported"),
    ]),
    ("Supplier risk", "Vendor risk manager", [
        ("How are critical subprocessors assessed before onboarding?", "Security and Privacy assess critical subprocessors for data access, hosting location, independent assurance and incident handling before production use. A named service owner accepts residual risk, and critical suppliers are reassessed annually or after a material incident.", "supported"),
        ("How are customers notified of new subprocessors?", "The subprocessor register identifies the service purpose, location and data categories. Subscribed enterprise contacts receive at least 30 days' advance notice of a planned addition, subject to the standard data processing terms. Objections are handled through the privacy review process.", "conditional"),
        ("Can infrastructure providers access customer content?", "The hosting provider operates the underlying infrastructure and may have access under its controlled operational procedures. MeridianDesk restricts application-level support access but does not claim that cloud-provider personnel are technically incapable of all access to stored content.", "shared responsibility"),
        ("Are support vendors permitted to download customer attachments?", "External support vendors do not receive production tenant credentials or attachment downloads by default. Any exceptional case requires customer authorization, a scoped support ticket and Privacy approval; anonymized diagnostic information is preferred.", "conditional"),
        ("What happens when a critical supplier is replaced?", "The service owner documents data migration, access revocation, credential rotation and deletion confirmation. Security verifies the exit checklist before closing the supplier record. A supplier replacement that changes data processing is also assessed for customer notice obligations.", "supported"),
    ]),
    ("API and interoperability", "API product manager", [
        ("Which public API resources are available?", "The REST API supports cases, contacts, comments, attachments and audit-event reads on eligible plans. Requests and responses use JSON except binary attachment transfers. There is no GraphQL endpoint and no direct SQL access to the production database.", "conditional"),
        ("What API rate limits apply?", "The default limit is 600 requests per minute per tenant, with a burst allowance of 100 requests. A limited request returns HTTP 429 with a Retry-After header. Higher sustained limits require capacity review and are not automatically included in Enterprise.", "conditional"),
        ("How are public API changes versioned?", "Breaking changes require a new major API version with at least 12 months' published deprecation notice for the previous supported version. Additive fields can be introduced within a major version, so clients must ignore unknown response fields.", "supported"),
        ("How are outgoing webhooks authenticated and retried?", "Webhook deliveries include an HMAC-SHA256 signature, event identifier and timestamp. Consumers should verify the signature and reject stale timestamps. Failed deliveries retry with exponential backoff for up to 24 hours; consumers must deduplicate by event identifier.", "supported"),
        ("What formats are available for a full tenant export?", "Tenant owners can request an asynchronous export containing case and contact JSON, CSV indexes and original attachment files in a ZIP archive. The download link expires after seven days. Exports omit internal security detections and data belonging to other tenants.", "supported"),
    ]),
    ("Integrations and product limits", "Integrations lead", [
        ("Is there a native Salesforce integration?", "The Enterprise Salesforce connector synchronizes selected account identifiers and case status in one direction from MeridianDesk. It does not copy attachment bodies or implement arbitrary bidirectional object synchronization. The customer supplies an appropriately scoped Salesforce integration account.", "conditional"),
        ("Can notifications be sent to Microsoft Teams or Slack?", "Customers can configure outgoing webhook notifications to a Teams or Slack workflow they manage. There is no vendor-hosted bot with access to all channel history. Customers control destination permissions and should avoid including sensitive case content in notification templates.", "conditional"),
        ("What is the maximum attachment size?", "An individual attachment can be at most 100 MB. Executable files and password-protected archives are blocked, and accepted uploads pass through malware scanning before download is enabled. Increasing the tenant storage quota does not increase the per-file size limit.", "supported"),
        ("Does the product support inbound email case creation?", "Each tenant can enable a generated inbound email address that creates new cases and appends replies to existing cases. Message size including attachments is limited to 25 MB. Customers can restrict accepted sender domains, but email ingestion is not an identity-verification mechanism.", "conditional"),
        ("Can tenants run custom server-side code inside the product?", "No. Tenants can configure routing rules and published webhook actions, but cannot upload executable plugins, database procedures or arbitrary server-side scripts. Custom processing must run in customer-managed middleware using the public API.", "not supported"),
    ]),
    ("Implementation and migration", "Implementation manager", [
        ("What is included in a standard implementation?", "Standard implementation includes a kickoff, tenant configuration, administrator training and one CSV import rehearsal. The typical plan spans four to six weeks after the customer supplies clean data and identity-provider access. Custom connector development is outside the standard scope.", "conditional"),
        ("Which historical data can be imported from a legacy system?", "The supported migration template accepts cases, contacts and comments through CSV, with attachments supplied in a mapped ZIP archive. Import does not preserve the legacy system's audit signatures or executable workflow rules. Trial imports run in a separate migration tenant.", "conditional"),
        ("What does the customer provide during onboarding?", "The customer names a project owner, supplies the user roster and role mapping, configures the identity provider and signs off on the migration sample. MeridianDesk cannot complete SSO setup without an authorized customer identity administrator.", "shared responsibility"),
        ("Is a sandbox environment included?", "Enterprise includes one sandbox tenant with synthetic starter data and separate API credentials. It is not automatically refreshed from production and must not receive unrestricted production exports. Starter plans do not include a persistent sandbox.", "conditional"),
        ("How is migration acceptance verified?", "Implementation compares source and imported record counts, samples relationships and attachments, and obtains customer acceptance before cutover. Failed rows are returned with row-level reasons for correction. A successful file upload alone does not constitute migration acceptance.", "supported"),
    ]),
    ("Support and operations", "Customer support lead", [
        ("What support hours are offered?", "Standard support operates Monday through Friday, 09:00 to 17:00 US Eastern time, excluding published holidays. Enterprise has continuous paging for Severity 1 service outages. Routine configuration questions submitted overnight wait for the standard support window.", "conditional"),
        ("How is a Severity 1 incident defined?", "Severity 1 means the production service is unavailable to most users of an affected tenant with no reasonable workaround. A single-user permission issue or a request for a new feature is not Severity 1. Support can reassess severity as impact changes.", "supported"),
        ("What initial response targets apply to support cases?", "Enterprise targets a 30-minute initial response for Severity 1 and four business hours for Severity 2. These are acknowledgement targets, not resolution-time guarantees. Standard-plan cases target one business day for an initial response.", "conditional"),
        ("How is planned maintenance communicated?", "Planned customer-impacting maintenance is normally announced at least seven days in advance on the status page. Emergency security maintenance may occur sooner. The maintenance window and any service-credit treatment are governed by the applicable subscription terms.", "conditional"),
        ("Can customers request an architecture or security review call?", "Enterprise prospects and customers can request a scoped review with Security or Architecture through their account team. Requests for internal diagrams, test results or supplier reports may require an NDA and redaction. A review call does not authorize new product commitments.", "conditional"),
    ]),
    ("Commercial and exit", "Legal and finance", [
        ("How are user licenses counted?", "Subscriptions count named active Agent and Administrator seats at the billing snapshot. Read-only Auditors are included up to the plan limit of 25. Shared logins are prohibited, and disabling a user affects the next billing snapshot rather than retroactively changing prior invoices.", "conditional"),
        ("Are data export fees charged at termination?", "A standard self-service tenant export is included during the 30-day post-termination retrieval window. Assisted transformations, repeated custom exports or third-party migration work may require a separate statement of work. No unlimited professional-services commitment is included.", "conditional"),
        ("Can customers negotiate a shorter breach notification deadline?", "A requested notification deadline that differs from the standard terms requires Legal and Security review. Account teams cannot accept a one-hour deadline or guarantee notice before an incident is verified. The signed agreement determines any customer-specific commitment.", "conditional"),
        ("Does the standard plan include a dedicated technical account manager?", "No. Enterprise can purchase a named technical account manager as an additional service with defined meeting cadence. The standard support queue remains the incident reporting path; a named contact is not a replacement for the on-call escalation process.", "not supported"),
        ("Will MeridianDesk accept unlimited liability for data incidents?", "No standard offer includes unlimited liability. Liability caps, indemnities and any higher data-protection cap require Legal approval in the signed agreement. A questionnaire response cannot amend those terms or create an insurance commitment.", "not supported"),
    ]),
]


def knowledge_records():
    records = []
    for category_index, (category, owner, entries) in enumerate(GROUPS, 1):
        for section, (question, answer, capability) in enumerate(entries, 1):
            records.append({"id": len(records) + 1, "category": category, "question": question,
                "answer": answer, "owner": owner, "capability": capability,
                "evidence_document": f"MD-{category_index:02d} — {category} operating guide (SIMULATED)",
                "evidence_section": f"{category_index}.{section}", "document_version": "2026.10-demo",
                "reviewed_on": "2026-10-29", "synthetic": True})
    return records


def rfp_cases():
    kb = {r["id"]: r for r in knowledge_records()}
    cases = [{"kind": "exact", "question": kb[i]["question"], "expected_evidence": [i]}
             for i in [11, 12, 14, 16, 21, 22, 26, 31, 36, 51, 63, 77]]
    for i, question in [
        (54, "Can administrators export tenant audit events using an API?"),
        (23, "Can an Enterprise customer bring its own encryption key?"),
        (27, "Can we move an existing tenant from US hosting to EU hosting?"),
        (44, "How are dependency versions pinned and scanned for vulnerable software?"),
        (71, "What security due diligence happens before a new critical subprocessor is used?"),
        (88, "Which tasks must our team complete during onboarding?"),
        (96, "Do read-only auditors consume paid Agent seats?"),
    ]:
        cases.append({"kind": "paraphrase", "question": question, "expected_evidence": [i]})
    for question, evidence, gap in [
        ("Does TLS encryption include customer client-certificate authentication on the public API?", [22, 24], "TLS versions alone do not establish public-edge mutual TLS support"),
        ("Can we use our own encryption key and immediately destroy every backup copy when we revoke it?", [23, 32], "Provider-managed encryption must not be represented as BYOK or instant backup erasure"),
        ("Can an EU tenant guarantee EU-only support access and zero cross-border processing?", [26, 28], "EU storage does not imply EU-only personnel access"),
        ("Does the one-hour recovery point objective also cover attachment loss after a regional disaster?", [63, 65], "Attachments have a different objective and there is no cross-region backup"),
        ("Can deleted records be kept on a configurable seven-year legal hold without exporting them?", [31, 34], "Recycle-bin retention does not establish native legal-hold support"),
    ]:
        cases.append({"kind": "compound-or-trap", "question": question, "expected_evidence": evidence, "gap": gap})
    for question in [
        "Is a VPAT accessibility conformance report available?",
        "Are customer records used to train generative AI models, and what opt-out controls exist?",
        "Is an SAP S/4HANA connector available with bidirectional purchase-order synchronization?",
    ]:
        cases.append({"kind": "missing-knowledge", "question": question, "expected_evidence": [],
                      "gap": "The initial scenario deliberately contains no approved answer"})
    cases.extend({"kind": "commitment-review", "question": kb[i]["question"], "expected_evidence": [i]}
                 for i in [6, 9, 100])
    assert len(cases) == 30
    return [dict(c, case_id=f"RFP-{i:03d}") for i, c in enumerate(cases, 1)]


LEARNED_ANSWER = ("No VPAT or independent accessibility conformance report is currently available for MeridianDesk. "
                  "The product team performs keyboard-navigation and screen-reader checks, but those internal checks "
                  "must not be described as a completed WCAG assessment or a published VPAT.")
