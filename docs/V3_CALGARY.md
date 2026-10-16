# Calgary equipment workflow, version 3.0

This release implements the equipment portion of the administrator's feedback. Calgary is the only configured branch. Vehicle forms, bay workflow, CV output and robot integration remain the partner's work. Existing vehicle code is retained for compatibility, not expanded by this release.

## How the application fits together

There is one React interface, one FastAPI backend and one PostgreSQL database. New capabilities are Python modules and database tables inside the same application, not separate microservices. The web server and its bounded background worker use the existing Azure deployment.

The permanent chain is Customer → physical Asset → individual Service Request → recorded Service Event. The product model, catalogue product number, serial number, Asset ID and service request number are separate. An additive migration moves old catalogue identifiers out of the model display field without replacing physical asset IDs or deleting histories.

Accounts and access are in `access.py` and `operations_models.py`. A Company and Calgary Location sit inside each isolated demo workspace. Named staff belong to that location; signed sessions recheck their active membership and version on every request. Changing a role or disabling an account revokes previous sessions. Demo persona switching only works for synthetic accounts. A public demo super-user is not the administrator's real production account. His own named super-user can be provisioned in a private deployment/account context once his email and deployment ownership are agreed.

| Role | Access |
| --- | --- |
| Reception | Calgary customers, equipment, intake, original scans, assignments, receipts/tags, parts enquiries, tracking; no internal AI review, knowledge import, report draft editing or final repair reporting |
| Technician | Calgary service records, internal documents, AI evidence review, approved checklists, drafts and actual repair reporting; may propose knowledge but cannot approve it or administer accounts |
| Super-user | Staff management, technical/privacy review of procedures, imports, corrections and audit/usage views; manufacturer means this administrative role |
| Customer | Own equipment wallet, owned QR routes, released documents, filtered history/guidance, symptoms and parts requests |

The separate organization repair role has been removed. Existing accounts are converted to customers without deleting assets or history. Open organization self-service requests return to reception as Unassigned; completed records remain unchanged. The former repair API and interface have been removed.

This is a proposed Calgary permission policy, not branch reviewers's final operational sign-off. Separate demo/company workspaces remain isolated. No cross-location sharing or Montreal accounts are created.

## Reception and technician work

Reception finds the existing customer by company, SAP customer code or an existing Asset ID. A customer confirmation is required before registration. The second pump receives a new Asset ID and QR code. SAP customer code and sale document type/number/line are manual references; nothing calls SAP.

Intake separates the owner from the drop-off contact, starts at Unknown / Not assessed and Unassigned, flags extraction uncertainty, requires review and warns about open visits. Accessories, damage, instructions and up to five photos have dedicated fields. Large JPG/PNG images are resized in the browser; the submitted file is retained. PDFs remain limited to five pages / 2.5 MB. These bounds need validation on actual paperwork, which has not been supplied. Receipt and equipment tag are print views of saved data, without AI. Reception can explicitly release an intake document to its owner after reviewing its suitability.

Technicians see the scanned paper, complaint, previous history and assistance together. Reports require actual diagnosis, work, verification, date and a deliberate outcome. Closing starts unchecked. Multiple parts have quantities and Used / Replaced / Requested actions. Unresolved or partly repaired work requires a reason. Drafts and waiting states support unfinished work.

## Approved knowledge and model structure

Markdown holds stable, sourced reference material, including selected product parts, product specifications and the business context. `knowledge/business/employee-experience.md` explicitly records that employee experience data is pending; it contains no invented qualifications. Not every Markdown file is placed into every prompt.

Changing operational data belongs in PostgreSQL. A Procedure has equipment applicability, symptom wording, a version, structured yes/no/unknown steps, source passages, solution limits, audience and review state. Technicians submit proposals. The super-user must check technical support and removal of private information before approval. Only approved procedures enter shared AI evidence. Approving a revised version retires the earlier one; old checklist answers remain in history. There is no fixed limit of 20 diagnostic issues.

The checklist runner follows stored branches, records observations and never invokes a language model. Matching an exact approved symptom bypasses automatic model generation for the staff workflow. Other applicable checklists appear immediately as choices. Completion does not confirm diagnosis or close a repair.

Optional AI uses targeted references, approved procedures and the specific asset's effective history. Gemini generates a structured draft. Code validates part and procedure identifiers and citations. A separate Gemini model reviews technical evidence. Customer privacy and communication quality are assessed separately from technical support. A recorded live judge failure led to a separate code-level gate: catalogue/component-list citations cannot justify diagnostic causes or candidate replacements; candidate numbers must also occur in the cited diagnostic source. Earlier-policy suggestions are withheld. Unsupported technical content is withheld; failed review explanations are labelled as rejected/non-actionable. A part reference match is not proof that replacement is necessary. No uncalibrated probabilities are displayed as fact.

Saving a report does not browse, train or call a model. It creates persistent history and a raw case record; wider knowledge requires a separately reviewed procedure. Corrections to reports are appended as amendments, preserving originals. AI reads amended history. A correction to a source repair retires an affected approved procedure for re-review. Audit records include actor, before/after values, time and reason, and the database rejects updates/deletes to the audit table.

## Operating costs and capacity

| Function | Trigger and processing | Cost behavior |
| --- | --- | --- |
| CRUD, wallet, search, QR, documents, receipts, report save | App + PostgreSQL | Hosting/storage; no model call |
| Approved checklist | Stored branches and answers | Database only; no token fee per step |
| Scan extraction | Upload of a scan, if configured and permitted | One external generation request; failure retains scan/manual entry |
| Photo attachment | Explicit intake photo upload | Storage only; no OCR call |
| Embeddings | Retrieval cache miss | Separate bounded external request; lexical fallback on failure |
| Recommendation | New eligible symptom / explicit follow-up, on cache miss | External generation request |
| AI evidence review | Successful draft generation | Separate external judge request |
| Cache hit | Unchanged evidence, identity, prompts and query | No provider request |
| Retraining / internet research | No automatic trigger | Not implemented |

The deployed setting AI_DAILY_LIMIT=30 is now a fallback for a shared ceiling of 30 provider HTTP requests per rolling day, not 30 complete recommendations. A separate per-workspace ceiling is 30, reserved-token ceiling 1,000,000 and concurrent provider ceiling 2. PostgreSQL reservations are taken before each actual call; errors and retries still consume reservations. Unknown provider token counts remain unknown. The token budget uses conservative input-size reservations, not a calibrated dollar estimate. OCR, embeddings, generator and judge all use the same ledger. Automatic guidance has at most two attempts. Approved procedures, records and reporting remain available at a limit or outage.

The existing F1 app plan is free, while the existing PostgreSQL server/storage consume Azure credit. Azure for Students spending protection is required by deployment tooling. No new infrastructure or paid model fallback was added. The exact remaining credit and a reliable monthly database charge are not asserted here. A free-tier model key must remain in a free-tier provider account; request limits cannot independently verify its billing status. Provider free quotas and availability may change. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

The F1 plan shares compute, can idle, and cannot scale out. Its in-app worker is demonstration infrastructure. Ten concurrent local read requests and concurrent provider reservations are tested; this does not establish production user capacity. Queue wait, memory and model throughput on the target machine still require load measurements. [Azure plan documentation](https://learn.microsoft.com/en-us/azure/app-service/overview-hosting-plans).

## Lemmer-controlled inference investigation

A possible next experiment is a local Ollama service on available Lemmer hardware. Its local API supports downloaded models without an external API key. This is an option to benchmark, not a claim that it is cheapest or already connected. [Ollama documentation](https://docs.ollama.com/api/introduction).

Before selecting a model, record CPU/GPU, RAM/VRAM, model/license terms and commercial-use conditions, quantization, measured tokens/second, first-token latency, OCR/multimodal requirements and concurrent queue wait. Include electricity, hardware depreciation, patching, backups, monitoring and staff support in cost comparison. Keep the generator and reviewer interfaces and source validation. Use the same frozen corpus/cases as the API baseline. Do not expose a local unauthenticated inference port to the public internet. No hardware, local model download or inference server was available from Lemmer in this session, so there is no fabricated local benchmark or hardware purchase recommendation.

## Evaluation and remaining acceptance

`python -m scripts.evaluate_retrieval --dataset evaluation/retrieval-synthetic.json --output result.json` runs keyword retrieval without models. Add `--ai` for a bounded comparison using the same equipment-filtered corpus and cases. Group/split overlap is rejected. Results retain unknown/failed calls and a corpus hash. This is separate from the existing A/B/C context comparison.

On five synthetic engineering examples, keyword retrieval matched expected behavior in four. Three live model calls completed and matched expected behavior, including one paraphrase missed by keyword search; two calls failed with HTTP 503. Those are three successful AI cases out of five attempted, not a claim of 100% accuracy. These visible fixtures are not unseen holdouts or diagnostic validation.

Still needed from Lemmer: actual intake papers/phone photos; complete repairs/manuals/procedures for the chosen family; employee lessons suitable for review; expected answers and separate holdout cases; branch reviewers's forms, assignment and closure approval. The students must confirm course requirements with their instructor. the administrator's operational sign-off cannot be generated by code. The private point-by-point completion report records these dependencies explicitly.
