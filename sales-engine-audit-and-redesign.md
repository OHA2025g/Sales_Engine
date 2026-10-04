# Sales Engine: repository audit and revenue workflow redesign

Audit date: 4 October 2026. Repository: OHA2025g/Sales_Engine. Audited main commit: `fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9`.

## Executive decision

Keep the existing application and stack. Redesign its business workflow, execution contracts, information architecture, and onboarding. A full rewrite would discard useful work without fixing the central problem.

The application has substantial CRM, AI, provider, governance, and post-sale functionality. It also has actual scheduled automation. Its central weakness is that these capabilities do not consistently form a reliable, policy-controlled revenue journey. Some modules produce drafts, approvals, activities, or demonstration metrics without completing the corresponding business outcome. Some important handoffs still need a person to initiate them. Several execution paths bypass the shared controls.

The intended product should feel like: “Set the sales strategy, approve its operating boundaries, connect the channels, and supervise the exceptions.” Today too much of the experience feels like: “Open each desk, choose a record, invoke an action, inspect another desk, then move the record yourself.”

The recommended product promise is **a governed revenue operating system for a defined customer segment**, covering market sensing, demand generation, sales execution, commercial closure, customer success, renewal, and expansion. Start with a proven segment and connected workflow rather than claiming unrestricted autonomous sales for every company.

## Assessment scope and limits

- Repository-wide inventory: 471 tracked files, including 259 Python files, 70 TSX files, 24 TS files, 72 Markdown files, and 49 Next.js page files.
- Reviewed navigation, page source and available actions, API routes, core lifecycle services, provider factories, worker scheduling, schemas/models, migrations/security architecture, documentation, tests, and CI definitions/results. Deeper execution tracing concentrated on the paths that connect acquisition to retention.
- Built the web application and ran the local API and web checks. Used isolated mock fixtures to reproduce specific workflow defects. No external messages, calls, advertisements, or social posts were sent.
- The local browser preview was blocked by the environment. This is a source-based website and interaction-flow assessment, not a rendered visual walkthrough. Responsive layout, visual polish, accessibility in a running browser, and actual provider UX remain unverified.
- No production database, credentials, production deployment, live campaign results, or real customer dataset were available. SQLite results do not establish PostgreSQL row-level security or concurrent-worker correctness.
- Historical gap reports in the repository predate later implementation. This report evaluates the audited commit and does not treat those old checklists as current defects.

## Validation results

| Check | Result | Interpretation |
|---|---|---|
| API pytest | 174 passed, 16 skipped, 250 warnings | Useful baseline; skipped PostgreSQL-dependent checks remain unverified locally. |
| API Ruff | Failed: two I001 import ordering violations | `app/api/v1/autonomy.py` and `app/seed.py`; simple delivery gate failures. |
| Web TypeScript | Passed | Existing frontend type checks pass. |
| Web Vitest | 4 tests passed, one test file | Small unit-test surface; this is not broad UI workflow coverage. |
| Next.js production build | Passed, Next 15.5.23 | Pages compile and production build succeeds. |
| OpenAPI generated contract check | Failed: drift | Generated specification and current API differ. |
| Latest GitHub CI at audited commit | Failed | Web, e2e-lite, image build, and secret scanning passed. API lint and OpenAPI failed. PostgreSQL-backed RLS, concurrency, and e2e jobs failed during seeding before their intended checks. |

Latest inspected run: [GitHub Actions run 37216605192](https://github.com/OHA2025g/Sales_Engine/actions/runs/37216605192).

The PostgreSQL seed failure is concrete: the showroom constructs `demo-board:{event_type}:{entity_id}` as a correlation identifier, while `DomainEvent.correlation_id` is `varchar(64)`. With `expansion.detected` and a UUID entity ID the value has 66 characters. PostgreSQL rejects it. This is a seed/schema mismatch, not evidence that RLS itself is absent or broken. Fix it before claiming the affected suites pass. [Source][R02] [Schema][R03]

## Existing work to preserve

| Area | Existing foundation | What to preserve |
|---|---|---|
| CRM | Accounts, contacts, leads, opportunities, tasks, activity trails | Existing entity model and audited mutations. |
| AI | Copilot, research/draft capabilities, model registry, knowledge grounding | AI as a bounded planner and assistant; deterministic code for business invariants. |
| Orchestration | Domain events, lead intake, due sequences, scheduled autonomy cycles | Evolve this into one consistent workflow engine. A scheduler already exists. |
| Controls | Tenant scoping/RLS implementation, role permissions, refresh-token families, encrypted provider credentials, signed webhooks | Harden and verify; do not replace with a simplified authentication system. |
| External execution | Provider actions, idempotency mechanisms, provider failure handling, channel stops, mock/live distinction | Apply these controls uniformly to every external action. |
| Commercial | Product catalog, decimal quote calculations, discount requests, close-won conversion | Complete approval-to-execution and contract evidence. |
| Customer lifecycle | Onboarding, health signals, renewal reconciliation, expansion, advocacy | Connect actual customer communications and reliable revenue measurements. |
| Operations | Run views, audit trail, pilot readiness, deployment/CI configuration | Turn inferred readiness into observed operational evidence. |

The repository describes production ML components as collecting data, not trained deployed predictors. Keep that distinction clear. Rule-based forecasting and ranking can be useful without marketing them as learned performance.

## Confirmed and high-confidence gaps

Severity: P0 = fix before unattended external execution or a release-readiness claim; P1 = necessary for the promised connected workflow; P2 = enterprise scale and product maturity. “Reproduced” means an isolated local mock fixture; “source” means a directly traced code path; “design gap” means the audited product surface does not provide the needed capability.

| ID | Priority / evidence | Gap and practical consequence | Required change |
|---|---|---|---|
| G01 | P0, reproduced | A domain-event handler exception still sets `processed_at`; the event disappears from pending work. Logging an error does not provide recovery. | Persist per-delivery retry status, attempts, backoff, dead letter, and replay; acknowledge only success or explicit terminal rejection. [R04] |
| G02 | P0, source | Pending events are selected without a claim lease or `SKIP LOCKED`. Domain event work can overlap across workers. Provider-action idempotency does not solve all workflow races. | Claim atomically, isolate each transaction, enforce unique execution keys, and test concurrent consumers. [R04] |
| G03 | P0, reproduced/source | Social/content publishing reaches its publisher despite the tenant emergency stop. Social credentials are resolved from process settings rather than tenant-bound connections. | Route publishing through the shared durable action executor, tenant credentials, approval policy, stops, quotas, and idempotency. The local reproduction used a mock publisher; no live publication occurred. [R05] [R06] [R07] |
| G04 | P0, source/CI | API lint, generated API drift, and PostgreSQL seeding currently break release checks. | Fix imports; regenerate and review the contract; bound/hash correlation IDs; run the blocked PostgreSQL suites to completion. [R02] [R03] |
| G05 | P1, reproduced | Intake selects the oldest eligible email sequence, including a draft. There is no segment/campaign/persona/product selection contract. | Only activated, versioned sequences may execute; use explicit routing rules and priority. An unmatched lead enters a visible configuration exception. [R04] |
| G06 | P1, reproduced | Setting `email_approval_required=false` still produces `WAITING_FOR_APPROVAL` and a pending approval. “Autopilot” does not implement the setting’s apparent promise. | Replace ambiguous booleans with scoped authorization grants and explicit observe/assisted/bounded-autopilot modes. [R04] [R08] |
| G07 | P1, reproduced | A blocked intake can be skipped as already processed after consent is corrected. Exception states participate in ordinal progression checks. | Separate progress from blocked/paused execution status; resume on the relevant fact-change event with a versioned evaluation key. [R04] |
| G08 | P1, source | Due sequence work handles email drafts; other step types can fail to advance. Outbound sequence execution is not a complete multi-step journey engine. | Implement registered step executors for send, wait, task, branch, meeting, and supported channels; reject unsupported steps at activation. [R04] [R09] |
| G09 | P1, source | Reply handling can prepare a meeting after a qualification call without using its qualification result. Questions/objections do not consistently suspend pending outreach. Delayed/out-of-office replies can leave stale send approvals. | Treat a reply as a state transition; cancel or revalidate competing actions; obey eligibility and resume dates again immediately before execution. [R10] [R09] |
| G10 | P1, source/design gap | Meeting preparation exists, but meeting outcome → sales-qualified opportunity → stage progression → proposal is not one consistently connected workflow. | Add explicit qualification/handoff rules, owner assignment, stage evidence, and a deal journey; do not create opportunities for every positive reply. [R04] [R11] |
| G11 | P1, source | Three exposed autonomy settings—campaign planning, deal monitoring, proposal preparation—are persisted/serialized but do not govern executing service logic in the audited source. | Implement and instrument their contracts or remove/label the controls until operational. Do not imply the underlying modules are absent. [R08] |
| G12 | P1, source | Playbook runs are operator-invoked; condition JSON is not evaluated by the runner. It supports task/activity/approval actions, and marks a run completed even with unsupported actions. | Event/condition matcher, validated action registry, versions, activation, run status derived from step outcomes, dry run and replay. [R12] |
| G13 | P1, reproduced | `quote.discount` has no dispatch handler. The approval can become approved while the quote remains draft and still requires approval. | Add a transactional handler with quote/version binding and discount-policy revalidation. Unknown action types must fail explicitly. [R12] [R13] |
| G14 | P1, reproduced | Customer `.send` approvals return an explanatory string rather than sending. Approval status is not proof that a customer communication happened. | Resolve the authorized customer contact and channel, persist delivery intent, execute, and expose delivered/failed/deferred separately from approved. [R13] |
| G15 | P1, source | Deferred or blocked execution can be conflated with an approved decision. An approved quiet-hour action needs durable resumption even if a ProviderAction was not yet created. | Separate approval records from executable ActionRequests; persist all approved actions before dispatch. [R13] [R09] |
| G16 | P1, source | Intelligence factories return mock company/contact/intent/news/technology providers. Live lead discovery exists separately; this does not make market intelligence live. | Add licensed/authorized sources, tenant connections, freshness/provenance, deduplication, and relevance routing. Exclude mock evidence from live decisions. [R14] [R15] |
| G17 | P1, source | Scheduled market scanning selects the first 20 accounts without a cursor. The same set can repeatedly receive attention. | Cursor or fair priority queue, per-account next-scan time, source budgets, backpressure, and tenant quotas. [R16] |
| G18 | P1, source | Content ad creation uses product list price as ad budget, falling back to 10. It creates a paused campaign, not a complete creative-to-live campaign flow. | Campaign budgets must come from an approved marketing plan; creative attachment, QA, scheduled activation, pacing, measurement, and controlled optimization. Do not equate paused creation with live spend. [R06] |
| G19 | P1, design gap | Content/social desks are disconnected operator actions; no complete campaign plan → calendar → approval → distribution → attributable response → learning loop. | Make content and distribution child executions of a campaign objective with shared assets, budget, audience, and attribution. [R06] [R07] |
| G20 | P1, source | Close-won sets customer ARR from opportunity amount and overwrites it on another win. Opportunity value need not equal annual recurring value. | Contract-line ledger, recurring versus one-time amounts, term annualization, amendments, customer rollup, and currency rules. [R17] |
| G21 | P1, source | Forecast labeled for the current month aggregates all open opportunities. The stage payload overwrites earlier amounts in the same stage. | Filter by forecast period/expected close, aggregate by stage/owner/category, store revisions, and show slippage/waterfall. [R12] |
| G22 | P1, source | GRR and NRR default to 1.0 for any customer population. A note acknowledges the placeholder, but the value still looks like measured 100% retention. | Return unavailable until a comparable opening cohort and amendments exist; calculate actual contraction, churn, and expansion. [R12] |
| G23 | P1, source | Some lifecycle lane failure counts are hardcoded and blocked counts reused across lanes. Automation ROI counts activity rows and mixes time windows. | Derive metrics from actual action/workflow outcomes, stage transitions, and comparable cohorts/time windows. [R18] [R19] |
| G24 | P2, source | RLS/backup readiness can be inferred from configuration presence. Worker/Beat signals are not equivalent to proven job continuity or a tested restore. | Readiness evidence includes database-role tests, backup restore record, oldest queue age, stale-run detection, and scheduler leadership. [R20] |
| G25 | P2, source | All-tenant job processing loops on a shared session; failure isolation and fairness are weak. Several lifecycle paths load broad `.all()` datasets. | Independent tenant transactions/jobs, limits, cursors, query budgets, indexes, and tested throughput targets. [R21] [R16] |
| G26 | P2, design gap | Auth/permissions exist, but enterprise identity and user lifecycle are incomplete in the exposed product: invitation, deactivation, delegated role management, SSO/MFA/SCIM need explicit implementation. | Phase identity features by target customers; test revocation and scoped administrative permissions. Avoid claiming enterprise identity simply because JWT exists. [R22] |
| G27 | P2, design gap | Sequence and playbook pages largely offer listing/enrollment/run rather than a complete authoring/activation/version workflow. Quote UI is narrower than backend multiline capability. | Usable builders, validations, version history, activation checklist, quote workspace, and audit-linked execution results. [R23] [R24] [R25] |
| G28 | P1, source/design gap | Navigation is organized by modules rather than the revenue lifecycle. Market is in More; deal risk, quotes, and forecast are under After the sale. | Replace the module catalog with journey workspaces and contextual detail navigation. [R01] |
| G29 | P1, design gap | Home emphasizes metrics/activity but does not consistently give an accountable, ranked cross-module exception queue. Technical phase labels and raw identifiers leak into product surfaces. | Business-language command centre, next action/reason/owner/deadline, role views, record names, and operational status. [R26] [R01] |
| G30 | P1, design gap | No complete company setup journey connects revenue objective, ICP, offer, budget, channel readiness, ownership, policies, and a dry run. | A revenue launch wizard and staged readiness gates; show what will run and why before activation. |
| G31 | P2, source/design gap | WhatsApp is mock/not-configured in the audited provider, and vendor-facing support/billing connections are not equivalent to a full self-service integration product. | Honest connector capability matrix, tenant setup, token refresh/health, mapping, retries, and sandbox proof. A signed webhook intake foundation already exists. [R27] |
| G32 | P1, design gap | Quote → proposal version → customer signature/acceptance → commercial close is incomplete as an evidence-driven lifecycle. | Proposal documents, permitted claims/terms, approval version binding, signature/acceptance integration, stage gates, and billing handoff as the target segment requires. [R12] [R17] |

## What the end-to-end product should do

Use one connected lifecycle with different execution lanes. Account, lead, opportunity, contract, and customer are separate business objects; a company may have many contacts, concurrent opportunities, and multiple contracts. Do not force these into one linear record.

1. **Plan:** define revenue objective, target segment, offer, territory, budget, owners, service expectations, channels, and operating policy.
2. **Sense:** collect relevant, fresh market/account evidence and identify where demand or customer risk is changing.
3. **Acquire:** create approved campaign plans; generate and schedule assets; capture attributed responses and imports/discovery records.
4. **Qualify and route:** resolve duplicates, enrich with evidence, evaluate eligibility and fit, choose owner and journey. A discovered contact is not automatically permitted for outreach.
5. **Engage:** execute a relevant approved sequence, handle replies, suppress conflicting actions, schedule meetings, and prepare the owner.
6. **Convert:** capture meeting outcome and sales qualification, create the opportunity, progress through evidence-based discovery/demo/value/procurement stages.
7. **Close:** generate and approve a versioned proposal/quote, obtain customer acceptance, record contract terms, and trigger the correct commercial/billing handoff.
8. **Deliver and retain:** launch onboarding, measure activation and health, resolve risk, conduct value reviews, and prepare renewal.
9. **Expand and learn:** identify evidence-backed expansion/referral opportunities and feed measured outcomes back into strategy, targeting, and workflows.

Each handoff needs a trigger, guard, owner, automatic action, deadline, completion evidence, recovery path, and escalation. An activity entry is supporting evidence; it is not completion of the handoff.

### First production workflow

Prove one complete inbound journey before broadening autonomy:

`capture.received → deduplicate → assess contact eligibility → enrich → qualify → assign owner → select activated journey → prepare grounded response → authorize → deliver → classify reply → book meeting → record outcome → create sales-qualified opportunity → prepare proposal → approve/send → record acceptance → activate customer → start onboarding → collect health evidence → renewal preparation`.

Expected business states must be visible alongside execution states. “Qualified” describes the lead; “waiting for authorization” describes the action. They must not be collapsed into a single status or success metric.

An incomplete qualification, missing consent fact, unavailable provider, or customer request for a person becomes an explicit exception assigned to the right owner. Fixing that exception resumes the workflow at the correct point, not at the start and not by resending previous actions.

### Required workflow library

| Workflow | Trigger | Automatic work | Human decision / completion evidence |
|---|---|---|---|
| Inbound speed-to-lead | Form, referral, inbound reply | Identity resolution, eligibility, enrichment, routing, suitable response, booking | Ambiguous qualification or sensitive commitments; actual delivery and booking result. |
| Target-account outbound | Approved ICP/campaign and eligible contact | Account research, personalized draft, activated sequence, follow-up scheduling | Campaign authorization; uncertain claims or eligibility; reply/outcome tracked. |
| Market-signal response | Fresh relevant signal | Link account, explain relevance, score fit, propose a journey | Source confidence and outreach eligibility; avoid reacting to mock/stale signals. |
| Content-led acquisition | Approved marketing objective | Brief, assets, review, calendar, distribution, capture attribution | Creative/budget authorization; attributable qualified response. |
| Reply and objection | Incoming message | Pause competing follow-ups, classify, draft factual answer, route | Pricing/terms/unsupported claims; actual sent answer or assigned conversation. |
| Meeting/no-show | Booking, completion or missed meeting | Preparation, reminder, outcome capture, reschedule/nurture | Qualification and promise-sensitive decisions; observed attendance/outcome. |
| Deal progression | Qualified outcome or stage evidence | Create opportunity, next-step task, evidence checklist, value case | Stage gates; owner confirms material facts and commercial commitments. |
| Quote follow-up | Approved proposal sent | Delivery tracking, expiry reminder, permitted follow-up | Discount/terms changes and acceptance; approved quote version. |
| Deal rescue | Slippage, inactivity or risk signal | Explain risk, prepare intervention, escalate SLA | AE/manager chooses recovery plan; measurable next step. |
| Customer onboarding | Accepted contract and activation eligibility | Handoff brief, plan, assignments, kickoff, milestones | Delivery owner accepts capacity/commitments; activation evidence. |
| Customer risk recovery | Trusted usage/support/billing evidence | Diagnose, propose recovery, contact authorized customer, track tasks | CS escalation and concessions; health movement and resolved issue. |
| Renewal, expansion, advocacy | Contract window or evidence-backed opportunity | Value summary, renewal preparation, related offer, referral request | Terms/customer authorization; signed renewal/accepted expansion or actual referral. |

No workflow may finish merely because it created an approval request. Unsupported actions must prevent activation. Failed steps must remain recoverable and visible.

## Proposed information architecture

Eight primary workspaces plus Settings. Retain existing routes initially through redirects and contextual links; avoid breaking bookmarks or rewriting all APIs merely to change navigation.

| Workspace | Existing modules/pages to place here | Additions needed |
|---|---|---|
| **Command Centre** | Home, actionable tasks, approval summaries, run exceptions | Ranked “needs your decision” queue, what is progressing, what is blocked, owner/SLA, target progress using trusted metrics. |
| **Strategy & Intelligence** | ICPs; Market overview, detail, signals, triggers; account intelligence; company/offer profile | Revenue objectives, territory/audience plans, opportunity hypotheses, source freshness and campaign recommendations. |
| **Marketing** | Campaigns, Content, Social, Acquisition, public capture pages | Campaign workspace with audience, assets, calendar, spend authorization, source attribution and qualified pipeline. |
| **Sales** | Leads/list/detail, Accounts/list/detail, Contacts/list/detail, Imports, Sequences, Conversations, Meetings, Voice scripts, Pipeline, Opportunity detail, Deal risk | SDR/AE queues, deal room, sequence builder, qualification/handoff, meeting outcomes, next-step enforcement. |
| **Commercial** | Commercial products and quotes | Proposal/quote detail, multiline editing, approvals, version history, acceptance/signature and contract workspace. |
| **Customers** | Customers/list/detail, Success, Renewals, Expansion, Advocacy | Onboarding plans, lifecycle timeline, stakeholder/contact mapping, customer communications, value reviews and measured cohorts. |
| **Autopilot** | Automation runs, Approvals, Playbooks | Policy grants, journey builder, execution inspector, recover/replay, dry run, quotas and emergency controls. |
| **Insights** | Forecast; revenue/automation metrics currently spread across pages | Pipeline movement, bookings/ARR/collections separately, attribution, cohort retention, action effectiveness, operating cost. |
| **Settings** | Knowledge, Models, Integrations, People, Teams, Flags, Audit, Pilot readiness | Company settings, data lifecycle, identity/access administration, source configuration and operational readiness. |

Intelligence/copilot should be a contextual panel available inside these workspaces, with an advanced research view when needed. It should not require users to repeatedly leave their deal or campaign to operate AI.

Support routes: login stays outside the app shell; public capture stays outside authentication; the coming-soon view should clearly disclose non-operational capabilities rather than appear as a functioning journey. Tasks should have a global queue and contextual record views. Approvals should have a central inbox and contextual cards in Commercial, Marketing, Sales, and Customers.

### Command Centre specification

The first screen should answer: **What is the system progressing? What needs me? What is blocked? What business outcome changed?**

- A quiet status header: autonomy mode, active strategy, connected channels, operational health, pause control.
- Primary panel: ranked exceptions and decisions. Every row shows the affected customer/account, reason, recommended action, owner, due time, impact basis, and evidence. Open the object in a contextual panel rather than send users searching across desks.
- Journey panel: observable work in acquire/engage/convert/deliver/retain lanes, with actual failure and waiting counts. Clicking a lane opens the work behind it.
- Outcome panel: trusted goal progress, qualified pipeline, accepted business, customer risk; unavailable metrics display unavailable, not fabricated performance.
- Activity is secondary. “Generated ten drafts” should not outrank “Proposal waiting on the buyer’s decision.”
- Role defaults: leadership sees targets/forecast/exceptions; marketing sees campaigns and attribution; SDR sees engagement/qualification; AE sees deal progression; CS sees onboarding/risk/renewal; admin sees operational controls.

### Record and deal-room specification

Each record shows the business state, accountable owner, next expected transition, relevant facts, evidence freshness, linked objects, and one timeline of human and automated decisions. Every automation action exposes “why,” policy version, source evidence, planned/executed/deferred/failed state, provider result, and recovery. Use human names and business wording; reserve internal IDs and raw payloads for an advanced inspection panel.

### Setup and activation

The launch wizard collects company/offer facts → objective → ICP/territory → channels and data sources → consent/eligibility policy → ownership/SLA → budgets and action caps → approved templates/playbooks → dry run → limited live activation.

It must show which journeys can actually run with current configuration. A connected provider is not equivalent to a ready campaign; a campaign needs an approved audience, assets, budget, and valid execution policy.

For attention and trust, replace phase-number labels with outcome language, use a coherent visual system, offer a guided fictional demo distinct from live work, and make the first approved strategy visibly progress through a journey. The differentiated product story is coordinated business execution with accountable controls, not the number of AI buttons.

## Execution architecture

Keep Next.js, FastAPI, PostgreSQL, Redis/Celery, and the existing storage/provider abstraction. Use a modular monolith with clear service boundaries until real workload constraints justify a split.

### Three layers

1. **Business planning:** goals, audiences, campaign plans, qualification rules, stage gates, playbook definitions, and AI proposals grounded in evidence.
2. **Workflow execution:** versioned journeys, event delivery, step states, routing, timers, SLA escalation, deterministic decisions, and human decisions.
3. **External action execution:** one durable policy-controlled path for email, calendar, ads, social, voice, customer communications, and future channels.

AI may propose actions or draft content. Typed code validates eligibility, money, permissions, stage transitions, recipients, and provider effects. An AI-generated plan is never itself authorization.

### Evolve these records

Reuse existing tables where suitable instead of creating parallel representations.

| Record/contract | Minimum purpose |
|---|---|
| Revenue objective | Segment, period, target measure, offer, budget, accountable owner. |
| Campaign plan | Objective, audience, channels, assets, schedule, attribution, authorization. |
| Versioned journey/playbook | Trigger, conditions, actions, branches, timers, policies, activation validation. |
| Journey links | Associate account, contacts, leads, opportunities, contracts and customer lifecycle without imposing one-to-one relationships. |
| Workflow execution / step | Definition version, business object, step state, attempts, last outcome, next due time, owner, blocker, replay metadata. |
| Event delivery | Event/schema version, consumer, causation, lease, attempts, backoff, terminal/retry status. |
| Action request | Approved intent, recipient/channel, policy grant/version, dedupe key, deadline, due time, provider id, result and reconciliation status. |
| Eligibility evidence | Source/consent or other applicable basis, suppression, scope, freshness, observed changes. |
| Stage evidence | Qualification, meeting outcome, customer acceptance, delivery readiness, and permitted transition. |
| Contract/revenue ledger | Recurring/one-time lines, currency, terms, effective dates, amendments and cohort calculations. |
| SLA clock | Due transition, owner/team, pause basis, breach, escalation and resolution. |

### State contracts

Lead business states: captured → assessed → qualified → engaging → meeting-ready → handed-off; nurture/disqualified are explicit business outcomes. Execution status is independent: queued, running, waiting, blocked, paused, failed, completed. Do not compare BLOCKED and PAUSED against business progress using ordinal indices.

Opportunity states: qualification → discovery → solution/value → proposal → negotiation/procurement → closed won/lost. Make stage definitions configurable within a versioned pipeline. Each transition validates evidence and records the owner and cause.

Customer states: onboarding → activated → healthy/at-risk → renewal-due → renewed/expanded/churned. Health is supported by observed source signals, with missing-data state rather than an invented reassuring score.

Approval states and execution states are separate. An authorization can be granted while an action is waiting for a permitted contact window. Display both. A rejected or expired approval never appears as an executed business outcome.

### Event and action reliability

- Write business mutation and outbox event in the same database transaction.
- Claim event work atomically using row locks/leases, with per-consumer uniqueness and independently committed processing.
- Retry transient errors with bounded backoff; expose terminal errors and dead letters; allow authorized replay with history.
- Persist intended external effect before calling a provider. Use a stable action key and provider idempotency where supported.
- Revalidate recipient eligibility, suppression, record version, deadlines, budget, authorization, pauses and channel readiness immediately before execution.
- If the provider call times out after possibly succeeding, reconcile using provider references before repeating. Do not promise universal exactly-once delivery where a provider cannot support it.
- Apply these invariants to direct UI commands and background jobs alike. Social and content cannot be a separate shortcut.
- Process tenants independently with quotas and fair scheduling. Use a service identity with bounded permissions rather than the first active user as the automation actor.
- Record observed step outcomes and timestamps. Alert on aging queues, missing expected transitions, repeated failures and expired approvals.

### Autonomy modes

| Mode | Permitted behavior |
|---|---|
| Observe | Research, score, recommend and simulate; external effects require explicit authorization. |
| Assisted | Execute individually approved actions or approved batches with a clear preview. |
| Bounded autopilot | Execute within a scoped grant: activated campaign/template version, permitted contact segment/channel, schedule, volume/cost caps, expiry, confidence/eligibility thresholds and escalation rules. |

Do not implement autopilot as a global “no approvals” switch. New spend, changed commercial terms, discount exceptions, unsupported claims, ambiguous recipients, and sensitive commitments require the configured accountable decision. Existing campaign actions can execute automatically within a valid grant, so humans are not asked to approve every predictable follow-up.

## Implementation sequence and acceptance criteria

These waves are dependencies, not promises of fixed calendar durations. Team size, integration scope, and target customer requirements determine effort.

### Wave 0 — make execution and validation truthful

1. Fix Ruff imports, OpenAPI drift, and showroom correlation IDs; complete the affected PostgreSQL suites.
2. Give unknown approval actions a failed/unavailable outcome; implement quote-discount handler with version checks.
3. Split authorization from execution; preserve approved-but-deferred work durably.
4. Put social/content through tenant-scoped policy and action execution; verify emergency stops across all channels.
5. Stop acknowledging failed domain events; introduce leases/retry/replay and meaningful failure status.
6. Replace placeholder retention and inaccurate lane counts with unavailable or computed values.

Acceptance: all CI required checks pass; no unknown action is displayed as successful; a killed/paused channel produces no mock or live external dispatch; failed events remain recoverable; quote approvals cause the correct audited quote state; seed replay remains bounded and idempotent.

### Wave 1 — prove one connected revenue journey

1. Implement activated sequence matching by ICP/offer/campaign; disallow draft selection.
2. Separate progress and exceptions; make fact changes resume appropriate steps.
3. Complete sequence wait/task/branch semantics and reply-driven cancellation/revalidation.
4. Connect inbound qualification, owner routing, authorized response, reply handling, meeting outcome and opportunity handoff.
5. Add ranked Command Centre exceptions, linked journey timeline and a minimal revenue launch wizard.
6. Add scoped authorization grants for the proven workflow.

Acceptance: a seeded eligible inbound lead reaches a properly qualified opportunity with no manual rescore/enrollment/record-moving; incomplete eligibility generates an owned exception; correcting it resumes once; repeated events, worker restart and concurrent jobs produce no duplicate effect in tested scenarios; every pause/decline/reply invalidates stale pending actions.

### Wave 2 — make sales and commercial closure complete

1. Versioned event-triggered playbook engine and usable sequence/playbook builders.
2. Configurable sales stages, evidence gates, owner/capacity routing, SLA clocks and escalation.
3. Deal room with meeting outcomes, stakeholders, next step, proposal preparation and risk.
4. Quote/proposal workspace, multiline edits, version-bound discounts/terms, sending/acceptance/signature flow.
5. Contract-based revenue ledger and period-correct forecast.

Acceptance: qualification evidence controls handoff; missing mandatory evidence blocks stage progression with an explanation; accepted proposal version matches contract; new wins do not overwrite customer recurring revenue incorrectly; forecast drill-down reconciles to contributing opportunities.

### Wave 3 — complete customer communications and retention

1. Accepted contract → accountable onboarding handoff and plan.
2. Customer contact/recipient resolver and actual governed success/QBR/renewal sends.
3. Fresh usage/support/billing signals with mapping, missing-data visibility and deduplication.
4. Risk recovery, renewal preparation and approved expansion journeys.
5. Cohort GRR/NRR and value-review evidence.

Acceptance: a won deal activates one customer lifecycle; duplicate close events do not create duplicate onboarding/renewals; resolved support incidents and signal corrections update health; customer sends have observable results; retention calculations reconcile to opening cohort and contract amendments.

### Wave 4 — connect market intelligence and marketing

1. Real, provenance-aware intelligence sources and fair account scan queue.
2. Objective-linked audience, offer and campaign planner.
3. Content calendar/assets and shared publish executor.
4. Approved budgets, creatives, channel activation and pacing.
5. Source/campaign/offer attribution and bounded optimization based on measured results.

Acceptance: mock evidence cannot trigger live decisions; product price never supplies ad budget; every campaign links to an objective and authorization; spend limits hold under concurrency; attributable leads flow into the proven sales journey; optimizations obey the campaign grant and require approval outside it.

### Wave 5 — enterprise readiness for the chosen market

1. Tenant onboarding, identity/user lifecycle, scoped admin controls, SSO/MFA where customer requirements justify it.
2. Data retention/export/deletion, audit access, migration discipline and restore testing.
3. Fair multi-tenant work queues, measured query performance, cursor APIs and appropriate indexes.
4. Observed scheduler health/leadership, run/watchdog alerts, tracing and provider reconciliation.
5. Staging soak, provider sandbox verification, role/RLS tests, failure/replay/concurrency drills and documented operating procedures.

Acceptance: actual RLS checks run with production-like application roles; access revocation works; restore is demonstrated; tenant load cannot starve another; required jobs stay within agreed SLA under measured load; no live-readiness badge appears without current evidence.

## Metrics that should replace decorative automation counters

| Metric | Definition / guardrail |
|---|---|
| Automation completion | Completed eligible action requests divided by evaluated eligible action requests in the same window; report failures and exclusions separately. |
| Human intervention | Required human decisions per completed journey, segmented by reason; distinguish healthy commercial approval from avoidable manual repair. |
| Speed-to-lead | Capture time to first authorized, actually delivered response, with median and tail. |
| Stage progression | Entry-to-exit time and conversion per stage/cohort, with pause reasons. |
| Qualified pipeline | Opportunity amount tied to explicit sales qualification and forecast period; currency-aware. |
| Accepted business | Accepted/signed bookings distinct from forecast, annual recurring value, and collected cash. |
| Customer activation | Contract activation to first defined value milestone. |
| GRR/NRR | Opening recurring-revenue cohort reconciled to churn, contraction and expansion over the same period. Unknown until input evidence exists. |
| Campaign effectiveness | Attributable qualified pipeline and accepted business alongside actual spend, not merely drafts/posts generated. |
| Reliability | Oldest queue age, retries, terminal failures, reconciliation backlog, stale runs, duplicate-effect incidents and recovery time. |
| Cost | Actual AI/provider/action cost per qualified opportunity and completed journey; no speculative “employee replacement” ROI. |

## Verification scenarios for the redesign

Tests should exercise business invariants and failure recovery rather than mirror service implementation.

1. Repeat capture/webhook delivery; a single business handoff and external effect result.
2. Run two workers on the same event/action; prove lease/uniqueness behavior in PostgreSQL.
3. Crash between intent persistence and provider result persistence; reconcile without blind repeat.
4. Change consent/suppression while a send awaits approval; execution refuses and the journey updates.
5. Receive an objection or out-of-office reply with an older send queued; old work is canceled or safely revalidated and rescheduled.
6. Correct a blocker; resume the right step and retain prior completed steps.
7. Approve a quote, then edit price/terms; stale authorization cannot authorize the new version.
8. Trigger stop/pause while each channel has queued work, including social; all external execution gates obey it.
9. Fail a tenant’s provider/database step; other tenants progress independently.
10. Replay close-won, onboarding, expansion and renewal events; no duplicate lifecycle records or revenue inflation.
11. Run forecast/retention against a known contract cohort including one-time fees, differing terms and currencies; reconcile expected totals.
12. Disable a user/role or integration; revoke subsequent access/execution and display a recoverable operational exception.

## Reproductions completed during this audit

Isolated SQLAlchemy mock fixtures produced these results; these are demonstrations of current behavior, not commits of corrective code:

| Scenario | Observed result |
|---|---|
| Sequence pool contains a draft | Selected sequence status: `draft`. |
| Email approval setting set false | `WAITING_FOR_APPROVAL`, one pending approval. |
| Consent corrected after blocked intake | `SKIPPED`, reason `already_processed`. |
| Discount approval accepted | Approval `approved`; quote `draft`; `approval_required=true`. |
| Content publish during tenant stop | Mock publisher reached; mock social post row created. No external publication. |
| Workflow handler raises | Failed event still marked processed; no remaining pending delivery in fixture. |
| Customer send approved | Approval accepted; result note says mapped contact needed; no customer send executed. |

## Recommended decision

Do not add more disconnected modules now. Fix execution integrity first, then prove a complete segment-specific revenue journey, redesign the interface around that journey, and expand intelligence/marketing/customer coverage through the same workflow and action contracts.

This report is a redesign specification and implementation backlog. The repository was inspected and validated without changing or pushing its source. The proposed interface is illustrative, not a functioning replacement application.

## Source index

All source references below are pinned to the audited commit. Findings labeled design gaps are conclusions from the exposed source and workflows, not claims about an uninspected production deployment.

[R01]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/web/src/components/shell.tsx#L42
[R02]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/seed_showroom.py#L585
[R03]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/models/identity.py#L143
[R04]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/orchestrator.py#L146
[R05]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/social.py#L45
[R06]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/content.py#L486
[R07]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/providers/social.py#L220
[R08]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/models/autonomy.py#L55
[R09]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/email_send.py#L27
[R10]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/reply_router.py#L50
[R11]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/api/v1/crm.py#L167
[R12]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/lifecycle.py#L139
[R13]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/dispatcher.py#L77
[R14]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/providers/intelligence.py#L143
[R15]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/market.py#L25
[R16]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/autonomy.py#L32
[R17]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/crm.py#L57
[R18]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/post_sale_reconcile.py#L236
[R19]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/roi.py#L57
[R20]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/services/pilot_readiness.py#L25
[R21]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/db/tenant_jobs.py#L13
[R22]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/api/v1/admin.py#L30
[R23]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/web/src/app/%28app%29/sequences/page.tsx#L15
[R24]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/web/src/app/%28app%29/playbooks/page.tsx#L15
[R25]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/web/src/app/%28app%29/commercial/page.tsx#L17
[R26]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/web/src/app/%28app%29/page.tsx#L15
[R27]: https://github.com/OHA2025g/Sales_Engine/blob/fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9/apps/api/app/providers/whatsapp.py#L53
