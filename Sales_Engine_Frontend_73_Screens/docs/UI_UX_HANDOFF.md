# Sales Engine — dark UI/UX design and implementation handoff

Designed for AGRAYIAN AI LABS. Date: 5 October 2026, IST. Reference repository audit: main commit `fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9`.

## Delivered scope

A complete interactive design prototype with **73 screens**, covering **all 49 existing repository page templates** and adding **24 workflow screens**. Every screen can be opened from All page designs or command search. Dynamic repository pages are represented by a concrete fictional record design. The new interface is a separate prototype, not a modification of the repository's running application.

All records, metrics, provider states, and action outcomes are illustrative. Actions change in-memory demonstration state only. No authentication, provider connections, email, social publication, advertising spend, calls, or production data mutation occur. Reloading resets demo state. Screens designed for currently incomplete backend capabilities do not imply those capabilities have been implemented.

## Product and visual direction

A serious daily working environment for revenue leadership, marketing, SDRs, account executives, customer success, and administrators. The design uses midnight and charcoal surfaces, restrained indigo actions, readable operational density, fine neutral borders, and limited corner rounding. It avoids a marketing-style hero inside the application, decorative illustrations, excessive gradients, oversized KPI tiles, and a catalog of disconnected AI buttons.

The memorable element is the visible revenue journey: accountable stages, exceptions, evidence, and next handoffs remain connected. The UI gives predictable work to the system while exposing the decisions that require a person.

### Foundation tokens

| Token | Value | Purpose |
|---|---|---|
| Canvas | `#0D1118` | Main application background |
| Sidebar | `#10151E` | Navigation and workspace identity |
| Surface | `#151C27` | Tables, panels, workspaces |
| Raised | `#1B2432` | Secondary controls and elevated content |
| Input | `#101722` | Editable fields and table headings |
| Border | `#293346` | Quiet structural separation |
| Main text | `#EEF2FA` | Primary content |
| Secondary text | `#A0AEC3` | Supporting information |
| Metadata | `#7E8DA4` | Nonessential annotation |
| Primary action | `#99A5FF` | Main action, current stage, selection |
| Success | `#8DD6B7` on `#18382F` | Observed completion or valid readiness |
| Review | `#F3CB85` on `#3D3223` | Decision, incomplete evidence, deferment |
| Blocked | `#FFABAE` on `#43272E` | Blocking risk or failed eligibility |
| Information | `#9DCAFF` on `#20354D` | Scheduled and progressing work |

Nine recurring text/background pairs were checked using relative luminance and exceed 4.5:1 contrast. This does not replace a complete rendered accessibility audit.

Typography: Inter with platform fallbacks. Body 16px; controls and tables 14px; metadata 12–13px; page titles approximately 28–30px. Use tabular figures for aligned money, dates, and counts. Use an eight-pixel spacing rhythm; panels generally use 20px internal padding. Corners are 6–8px, with shadows reserved for dialogs and mobile overlays.

Status color always accompanies a readable label. Success means an observed outcome, not merely a recommendation, queued task, or approval. Business state and execution state are shown separately.

## Information architecture

Eight business workspaces plus Settings:

| Workspace | Primary responsibility |
|---|---|
| Command Centre | Progress, owned exceptions, decisions, expected outcomes, role views |
| Strategy & Intelligence | Revenue objective, offer, ICP, market/account evidence, triggers |
| Marketing | Campaign plan, content, distribution, calendar, capture, attribution |
| Sales | Lead qualification, accounts/contacts, engagement, meetings, pipeline, deal room |
| Commercial | Catalog, proposal, quote versions, authorization, acceptance, contract |
| Customers | Onboarding, value, health, recovery, renewal, expansion, advocacy |
| Autopilot | Playbooks, scoped policies, executions, decisions, recovery and pauses |
| Insights | Period forecast, attribution, recurring cohorts, automation reliability and cost |
| Settings | Workspace, launch, providers, knowledge, access, AI governance, audit and readiness |

The sidebar exposes primary workspaces and context-relevant secondary navigation. All page designs is a prototype review utility; it need not ship in the production product. The command search finds every page. Contextual AI opens with the current record rather than forcing the user into an unrelated AI desk.

The top bar provides breadcrumbs, search, role preview, decision inbox, and contextual copilot. The screen header states the business purpose, primary action, and next handoff. Detail pages expose linked objects rather than raw database IDs.

## Core workflows and review paths

### Revenue launch

Company and approved offer → revenue objective and audience → connections and ownership → policies and limits → dry run and limited activation. Five setup steps demonstrate the required launch experience. Activation must be server-validated in the production implementation.

### Market to demand

Strategy → approved ICP → relevant fresh account evidence → campaign brief → audience and budget plan → grounded assets → asset review → schedule/distribute → attributed capture. Campaign budgets are separate from product pricing. A connected advertising account is not a campaign authorization.

### Lead to sales-qualified opportunity

Acquisition → identity and eligibility → qualification and owner → activated journey → authorized response → contextual reply → meeting preparation → verified outcome → opportunity. The meeting design explicitly distinguishes qualified, needs more evidence, nurture, and disqualified outcomes. Only a qualified outcome opens the opportunity handoff in the demonstration.

### Opportunity to accepted business

Deal room → proposal → multiline quote → authorize exact quote version → observe delivery → record buyer acceptance → contract → customer handoff. The quote prototype demonstrates that approval does not mean sent. Material edits increment the version and invalidate prior authorization. Pausing prevents example dispatch. The contract separates recurring and one-time line values rather than assigning total opportunity amount to ARR.

### Accepted business to customer activation

Contract acceptance → named delivery and customer owners → handoff acknowledgement → kickoff → data readiness → first value evidence. Onboarding milestones progress in order and retain evidence of completion.

### Customer risk and renewal

Fresh usage/support/billing evidence → owned recovery plan → authorized stakeholder communication → observed recovery/activation → value review → renewal proposal → accepted amendment. Customer risk is explained by source evidence. Missing health data is unavailable, not automatically healthy. Expansion is deferred if required activation/value evidence is incomplete.

### Workflow inspection and recovery

Execution centre → versioned journey steps → current evidence guard → approval or provider result → deferred/recoverable/terminal outcome → authorized replay. Completed effects remain retained during recovery. Emergency pause is cross-channel. Policy grants are scoped to audience, version, channel, limits and expiry.

## Role views

| Role | Default attention |
|---|---|
| Revenue manager | Objective progress, forecast, cross-team decisions and exceptions |
| Marketing manager | Campaign authorization, assets, distribution, attributed demand |
| Sales development | Eligibility, qualification, replies, meetings, owned lead work |
| Account executive | Buyer evidence, deal stages, next steps, proposal and commercial decisions |
| Customer success | Activation, dependency recovery, value reviews, renewal readiness |

The role selector previews different Command Centre priorities. It does not implement or prove production role-based access control. Production visibility and permissions must be enforced by the existing API and tenant context, not client-side filters.

## Page pattern library

The page set includes working command centres, list/search/filter tables, account/lead/contact records, market briefs, campaign workspaces, content cards and editors, distribution calendars, acquisition sources, import validation, sequence/playbook builders, threaded conversations, meeting outcomes, voice readiness, pipeline boards, deal rooms, commercial quotes, proposal editors, contract handoffs, onboarding milestones, health recovery, renewal plans, execution inspectors, policy grants, forecasts/cohort reconciliations, connection cards, administration, public capture and login.

Lists support record selection and locally filtered results. Detail pages display context, owner, evidence, next action, linked objects and timeline. Builders disclose activation, authorization, stop and failure behavior. Publishing surfaces show scheduled, reviewed, delivered and failed as separate states. Commercial screens bind authorization to the reviewed version. Operational readiness displays verification evidence and blocks unsupported claims.

## Component behavior and states

Shared components: primary/secondary/disabled controls; semantic tables; search/filter toolbar; breadcrumbs; contextual tabs; status labels; progress indicators; evidence checklists; timelines; record avatars; native dialogs; mobile navigation; transient feedback; forms with labels; primary/secondary work panels.

The Design system page provides empty, loading, recoverable failure and completed previews. Empty states explain the first meaningful action. Failure states explain the uncertainty and recovery rather than merely displaying “something went wrong.” Provider timeouts must reconcile possible success before repeating an effect. Destructive pause controls require confirmation. Modal dialogs retain native keyboard and focus behavior. Escape closes them.

Use confirmation for destructive or cross-channel changes, not for every reversible draft edit. Surface version invalidation immediately when terms or content change. Preserve unsaved edits in the production implementation before navigating away; the prototype does not implement full form persistence.

## Responsive and accessibility requirements

Desktop: fixed-width primary navigation, sticky context header, wide work panels and dense tables. Medium widths collapse multi-panel layouts and reduce auxiliary header content. Mobile uses a navigation drawer, stacked forms/panels, wrapped actions and horizontally contained tables/pipeline boards. Touch controls have larger effective targets. Reduced motion preferences are respected.

Semantic labels, status text, dialog names, table headers, keyboard focus and search empty states are implemented in the prototype. Browser QA must verify small viewports, 200% text enlargement, focus order, dialog focus restoration, screen reader output, table/pipeline scrolling and font loading. Do not treat source-based responsive CSS checks as visual verification.

## Implementation in the existing repository

1. Port shared tokens into the existing web globals and Tailwind theme without replacing the backend.
2. Implement the shell and workspace navigation using existing authenticated tenant/permission context.
3. Create reusable components for page header, record context, exception queue, evidence checklist, timeline, business/execution states and linked handoffs.
4. Migrate the existing routes into these layouts incrementally. Keep bookmarks through redirects or aliases where routes change.
5. Bind forms to typed schemas and existing query/mutation patterns; add full loading, error, validation, pending and success states.
6. Implement the missing backend handoffs and durable action contracts from the earlier audit. A newly designed page is not an execution engine.
7. Keep actor and object names readable; reserve raw payloads, provider IDs and correlation details for advanced inspection.
8. Separate feature controls, role permissions, connection readiness and action authorization. Never let a UI switch bypass server rules.
9. Calculate metrics from the same tenant, currency, period and evidence basis. Return unavailable where calculation inputs are missing.
10. Run the production route, role, responsive and provider-state tests after binding the prototype to the real application.

## Validation completed

- All 73 screen renderers produce substantive page structure in a simulated DOM.
- All 49 original route templates map to a design; no source page is omitted.
- 1,816 internal links across rendered screens resolve to registered page designs.
- No duplicate element IDs or missing labeled form controls were detected in the page pass.
- Demonstration checks passed for authorization/delivery separation, quote-version invalidation, pause guard, qualified meeting handoff, acceptance to onboarding, ordered milestones, search and empty results, launch setup and role priorities.
- JavaScript syntax checks passed.
- Two optional structured navigation/read tools were checked in the simulated DOM, including valid input/state read-back and invalid input rejection. Supported-browser validation was unavailable.
- Visual browser rendering, actual responsive appearance, screen reader behavior, production authentication, provider execution and backend integration are not verified by this prototype.

## Complete screen directory

Existing routes refer to the audited repository. Added screens provide explicit workflow and authoring handoffs. Each prototype route can open independently.

| Page | Workspace | Repository route | Prototype route | Next handoff |
|---|---|---|---|---|
| Overview | command | / | `#/home` | Decision inbox |
| Revenue journey | command | Added workflow screen | `#/flow` | Inbound journey · Meridian |
| Revenue strategy | strategy | Added workflow screen | `#/strategy` | Ideal customer profiles |
| Ideal customer profiles | strategy | /icps | `#/icps` | Market overview |
| Market overview | strategy | /market | `#/market` | Signal inbox |
| Account intelligence | strategy | /market/[id] | `#/market-detail` | Enterprise AI · campaign |
| Signal inbox | strategy | /market/signals | `#/signals` | Signal triggers |
| Signal triggers | strategy | /market/triggers | `#/triggers` | Campaigns |
| Campaigns | marketing | /campaigns | `#/campaigns` | Enterprise AI · campaign |
| Enterprise AI · campaign | marketing | Added workflow screen | `#/campaign-detail` | Content studio |
| Content studio | marketing | /content | `#/content` | Content editor |
| Content editor | marketing | Added workflow screen | `#/content-editor` | Marketing calendar |
| Social publishing | marketing | /social | `#/social` | Marketing calendar |
| Marketing calendar | marketing | Added workflow screen | `#/calendar` | Inbound acquisition |
| Inbound acquisition | marketing | /acquisition | `#/acquisition` | Leads |
| Leads | sales | /leads | `#/leads` | Lina Shah · lead |
| Lina Shah · lead | sales | /leads/[id] | `#/lead-detail` | Conversations |
| Accounts | sales | /accounts | `#/accounts` | Meridian Logistics |
| Meridian Logistics | sales | /accounts/[id] | `#/account-detail` | Meridian · deal room |
| Contacts | sales | /contacts | `#/contacts` | Lina Shah · contact |
| Lina Shah · contact | sales | /contacts/[id] | `#/contact-detail` | Lina Shah · lead |
| Import centre | sales | /imports | `#/imports` | Leads |
| Outreach sequences | sales | /sequences | `#/sequences` | Sequence builder |
| Sequence builder | sales | Added workflow screen | `#/sequence-builder` | Autonomy & policies |
| Conversations | sales | /conversations | `#/conversations` | Meetings |
| Meetings | sales | /meetings | `#/meetings` | Meridian · discovery |
| Meridian · discovery | sales | Added workflow screen | `#/meeting-detail` | Meridian · deal room |
| Voice workspace | sales | /automation/voice-scripts | `#/voice` | Meridian · discovery |
| Opportunity pipeline | sales | /pipeline | `#/pipeline` | Meridian · deal room |
| Meridian · deal room | sales | /opportunities/[id] | `#/opportunity-detail` | Meridian · quote Q-1042 |
| Deal risk | sales | /deals | `#/deals` | Meridian · deal room |
| Work queue | sales | /tasks | `#/tasks` | Confirm buyer success criteria |
| Confirm buyer success criteria | sales | /tasks/[id] | `#/task-detail` | Meridian · deal room |
| Quotes & catalog | commercial | /commercial | `#/commercial` | Meridian · quote Q-1042 |
| Meridian · quote Q-1042 | commercial | Added workflow screen | `#/quote-detail` | Decision inbox |
| Proposal workspace | commercial | Added workflow screen | `#/proposal` | Meridian · quote Q-1042 |
| Contracts | commercial | Added workflow screen | `#/contracts` | Meridian · contract |
| Meridian · contract | commercial | Added workflow screen | `#/contract-detail` | Onboarding |
| Customer portfolio | customers | /customers | `#/customers` | Cedar Health · customer |
| Cedar Health · customer | customers | /customers/[id] | `#/customer-detail` | Customer success |
| Onboarding | customers | Added workflow screen | `#/onboarding` | Cedar Health · customer |
| Customer success | customers | /success | `#/success` | Cedar Health · customer |
| Renewals | customers | /renewals | `#/renewals` | Cedar · renewal plan |
| Cedar · renewal plan | customers | Added workflow screen | `#/renewal-detail` | Meridian · quote Q-1042 |
| Expansion | customers | /expansion | `#/expansion` | Meridian · deal room |
| Advocacy | customers | /advocacy | `#/advocacy` | Cedar Health · customer |
| Execution centre | autopilot | /automation/runs | `#/runs` | Inbound journey · Meridian |
| Inbound journey · Meridian | autopilot | Added workflow screen | `#/run-detail` | Lina Shah · lead |
| Decision inbox | autopilot | /automation/approvals | `#/approvals` | Meridian · quote Q-1042 |
| Journey playbooks | autopilot | /playbooks | `#/playbooks` | Playbook builder |
| Playbook builder | autopilot | Added workflow screen | `#/playbook-builder` | Execution centre |
| Autonomy & policies | autopilot | Added workflow screen | `#/policies` | Execution centre |
| Revenue forecast | insights | /forecast | `#/forecast` | Opportunity pipeline |
| Campaign attribution | insights | Added workflow screen | `#/attribution` | Enterprise AI · campaign |
| Customer cohorts | insights | Added workflow screen | `#/retention` | Renewals |
| Automation performance | insights | Added workflow screen | `#/automation` | Execution centre |
| AI research workspace | command | /intelligence | `#/intelligence` | Meridian · deal room |
| Company & workspace | settings | Added workflow screen | `#/company` | Revenue launch |
| Revenue launch | settings | Added workflow screen | `#/setup` | Revenue strategy |
| Knowledge library | settings | /knowledge | `#/knowledge` | Content editor |
| AI & model governance | settings | /models | `#/models` | Operational readiness |
| Connections | settings | /admin/integrations | `#/integrations` | Revenue launch |
| People & access | settings | /admin/users | `#/users` | Teams & ownership |
| Teams & ownership | settings | /admin/teams | `#/teams` | Autonomy & policies |
| Feature controls | settings | /admin/flags | `#/flags` | Operational readiness |
| Audit trail | settings | /admin/audit | `#/audit` | Inbound journey · Meridian |
| Operational readiness | settings | /admin/pilot | `#/pilot` | Revenue launch |
| Security & data | settings | Added workflow screen | `#/security` | Operational readiness |
| Design system | settings | Added workflow screen | `#/design-system` | All page designs |
| All page designs | settings | Added workflow screen | `#/screen-index` | Revenue journey |
| Capability availability | settings | /coming-soon/[engine] | `#/coming-soon` | Connections |
| Sign in | settings | /login | `#/login` | Overview |
| Public capture form | marketing | /capture/[token] | `#/capture` | Lina Shah · lead |
