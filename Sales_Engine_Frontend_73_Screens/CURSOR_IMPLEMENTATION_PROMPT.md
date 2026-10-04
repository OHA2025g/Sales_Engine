# Cursor implementation prompt

Paste the following instructions into Cursor Agent with the existing Sales_Engine repository open. The default reference path is `design-reference/Sales_Engine_Frontend_73_Screens/`; locate the package by its `START_HERE.md` if you extracted it elsewhere.

---

Implement the complete dark Sales Engine UI/UX redesign in this existing repository. The reference package contains the full source for 73 screens: all 49 original repository page templates plus 24 workflow/design screens. Implement the full manifest, not just the home page and sidebar.

## Goal

Preserve the working application while replacing its fragmented module-based experience with the connected revenue workspaces in the design. Match the reference layout, dark palette, typography, spacing, density, component states, record context, and page-specific composition. The application should feel like a serious enterprise revenue workspace.

## Read before editing

1. Follow repository `AGENTS.md` instructions if present. Inspect the current branch and preserve unrelated work.
2. Read the supplied `START_HERE.md`, `docs/UI_UX_HANDOFF.md`, `docs/INTEGRATION_NOTES.md`, `docs/SCREEN_MANIFEST.json`, and `docs/ROUTE_MAPPING.csv`.
3. Read the complete `prototype/style.css`, `prototype/data.js`, and `prototype/app.js`; use `preview/sales-engine-all-73-screens.html` to inspect the exact reference. `FULL_FRONTEND_CODE.md` contains the entire source in a single text file if convenient.
4. Inspect the CURRENT repository, including its frontend page routes, shared UI components, shell, authentication, permissions, SDK, types, API hooks, and server endpoints. The package references an earlier audited commit; current implementation is authoritative where it has changed.
5. Read `docs/REPOSITORY_AUDIT.md` for known workflow gaps. Do not assume those gaps are already fixed merely because a screen has been designed.

## Implementation boundaries

- Keep the existing Next.js + React + TypeScript frontend and existing backend stack. Port the design into native components; do not replace the application with an iframe, static HTML wrapper, hash-router app, or `dangerouslySetInnerHTML` implementation.
- Preserve login/session restoration, tenant isolation, permission checks, existing provider integrations, API contracts, auditing, and working business functionality.
- Reuse the declared UI primitives, icon library, query client, forms, validation, SDK, and type definitions. Do not install a new UI framework or rewrite dependency manifests merely for this redesign.
- Do not replace live API requests with the reference's example arrays or in-memory state. Fixture data belongs only in clearly labeled development previews. Normal production screens must show real data or an honest empty/unavailable state.
- Client-side switches and role previews are not production authorization. Retain server-enforced permissions and eligibility. Keep money and action policy checks on the server.
- Do not alter database/security infrastructure or rewrite backend services as incidental UI work. If a required handoff needs an endpoint that does not exist, document the exact missing contract and show the action as unavailable with a useful reason. Implement the designed UI around a typed integration boundary. Do not invent successful responses or fake external effects.
- Existing dynamically routed records must use real route parameters and selected entities. Do not hardcode Meridian, Lina, Cedar, example IDs, currencies, quote terms, or portfolio metrics into the production UI.

## Workspace organization

Use these eight primary business workspaces plus Settings:

1. Command Centre — owned decisions, exceptions, journey progress, goal outcomes, role-specific attention.
2. Strategy & Intelligence — objectives, offers, ICPs, evidence, signals, triggers, account research.
3. Marketing — campaign plans, grounded assets, publishing, calendar, capture, attribution.
4. Sales — leads, accounts, contacts, imports, sequences, conversations, meetings, voice readiness, pipeline, deal rooms, tasks.
5. Commercial — catalog, quote/proposal versions, commercial approvals, acceptance, contracts.
6. Customers — onboarding, customer context, health, recovery, renewals, expansion, advocacy.
7. Autopilot — definitions, executions, decision inbox, scoped grants, recovery and pauses.
8. Insights — period forecast, attribution, customer cohorts, execution performance and cost.
9. Settings — workspace launch, connections, knowledge, people, teams, security, model governance, release controls, audit and readiness.

Preserve existing routes where possible; add routes for the workflow screens and compatible redirects where navigation changes. Use `docs/SCREEN_MANIFEST.json` as the page-level acceptance inventory. Proposed added routes are suggestions; inspect actual routing and avoid collisions.

## Visual requirements

- Dark canvas `#0D1118`, sidebar `#10151E`, panels `#151C27`, raised surfaces `#1B2432`, borders `#293346`.
- Main text `#EEF2FA`, supporting text `#A0AEC3`, restrained indigo action `#99A5FF`.
- Inter or a visually equivalent locally supported font; system fallback. Body 16px, controls/tables 14px, metadata 12–13px, page titles around 28–30px.
- Compact enterprise density, fine borders, 6–8px corner radius, and shadows primarily for overlays. No marketing hero inside operating workspaces.
- Status color accompanied by explicit text. Clear disabled, pending, empty, loading, blocked, error and completed states.
- Use the different layouts in the reference: operational lists, deal rooms, pipeline boards, content editors, calendars, conversation threads, builders, financial documents, health evidence, and administrative controls. Do not flatten all 73 screens into the same generic card page.
- Responsive layout, contained table/board overflow, usable mobile navigation, keyboard focus, proper labels and semantic dialogs. Check reduced motion and 200% text enlargement.

## Connected interaction requirements

Implement real navigation and relevant state transitions wherever the current backend supports them:

- Capture → qualification/eligibility → owner routing → activated sequence → response/conversation → meeting outcome → qualified opportunity.
- Opportunity → proposal/quote → version-bound authorization → execution/delivery result → buyer acceptance → contract → accountable onboarding.
- Onboarding → activation evidence → customer health/recovery → value review → renewal/expansion.
- Strategy → approved campaign plan → assets → review → scheduling/distribution → attributed capture → qualification.
- Each record shows an accountable owner, business state, execution state, evidence, next expected transition and linked objects.
- “Approved” is distinct from “sent,” “published,” or “completed.” Unknown or failed action outcomes must not appear successful.
- Material quote/asset changes invalidate obsolete authorization where the backend contract requires it; respect the actual current version contract.
- Reply/opt-out/pause must invalidate or defer incompatible pending work; UI should reflect server state rather than claim unsupported automation.
- A corrected blocker should expose the correct resume action without repeating completed effects.
- All external action entry points respect channel readiness, eligibility, authorization, pauses and role permissions enforced by the backend.
- Scoped autonomy grants are not a global approval-bypass boolean.
- Forecast, ARR, GRR/NRR and automation metrics use supported evidence and consistent periods/currencies. Return unavailable if inputs are missing; do not port demonstration metrics.

## Execution sequence

1. Create the shared tokens, accessible component patterns, redesigned shell, workspace navigation, contextual links and Command Centre.
2. Migrate all existing routes, maintaining real read/write integration and permissions. Ensure record detail pages are included.
3. Implement the 24 added screens using the manifest. Exclude the two review utilities from ordinary production navigation or guard them for development/admin preview.
4. Connect available workflows and expose missing backend contracts honestly.
5. Add page-level loading/empty/error/pending states and complete responsive/accessibility checks.
6. Verify the entire page inventory and meaningful lifecycle interactions.

Continue until the full scope is implemented or a concrete dependency blocks an action. Do not stop after a cosmetic global theme change or a single representative page. For an unavailable backend capability, finish the UI and typed boundary, document the gap, and avoid a fake result.

## Verification and handoff

- Use the repository's existing package manager and appropriate commands. Run frontend type checking, production build, and the relevant existing tests. Add focused verification where a real workflow change warrants it.
- Validate all 49 original route templates and all added operational screens. Check permissions with representative roles, selected real entities, loading/empty/error states, and mobile/desktop layouts.
- Check quote authorization versus execution, stage handoffs, contact suppression, pauses, and accurate metric absence where contracts support them.
- Create a frontend page-coverage report listing each screen, route, implementation status, API binding, permission and remaining dependency.
- Document missing API contracts in a clearly named frontend API-gap report. Explain actual limitations without claiming production readiness from the design alone.
- Summarize changed files, validation results, implemented workflows and unresolved dependencies. Preserve the prior source-backed audit as historical context rather than copying its findings as new failures.

The expected output is a coherent native Next.js frontend matching the supplied dark reference across the entire product, integrated with the real application wherever its current backend allows.
