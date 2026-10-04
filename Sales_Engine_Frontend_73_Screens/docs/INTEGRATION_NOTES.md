# Frontend integration notes

## Existing target stack at the audited commit

- Next.js 15, React 19, TypeScript and Tailwind.
- Existing workspace packages: `@agrayian/sdk`, `@agrayian/types`, `@agrayian/ui`.
- Existing declared libraries include TanStack Query/Table, Lucide React, React Hook Form, Zod and Recharts.
- Main frontend pages: `apps/web/src/app/(app)/.../page.tsx`.
- Public login and capture pages: `apps/web/src/app/login/page.tsx` and `apps/web/src/app/capture/[token]/page.tsx`.
- Shell: `apps/web/src/components/shell.tsx`.
- Session/permissions: `apps/web/src/lib/auth.tsx`; existing `useAuth()` and `can(permission)`.
- API/query patterns: `apps/web/src/lib/hooks.ts`, `packages/sdk/src/index.ts` and existing routes/types.

Inspect current files rather than assuming these paths or versions have remained unchanged.

## Porting the reference

| Prototype source | Native implementation |
|---|---|
| `style.css` root tokens | Shared dark CSS variables / existing Tailwind theme |
| `shell()` | Authenticated app shell, sidebar, breadcrumb, search and contextual panel components |
| `SCREENS`, `WORKSPACES` | Typed navigation/route metadata plus permissions |
| `TABLES` | Table column definitions; actual typed API query results |
| Individual render functions | React feature/page components, preserving each page's distinct composition |
| `location.hash` links | `next/link`, router navigation, current pathname and real record parameters |
| `state` | API-backed server state, typed mutations and minimal view-local React state |
| Demo role picker | Optional preview-only control; actual access from authenticated roles |
| `modal()` | Existing accessible dialog/sheet primitives and controlled form state |
| `act()` | Feature-specific mutation handlers with pending/error/result states |
| Local statuses/fixtures | Actual business state, approval state and provider execution results |

## Suggested feature boundaries

Shared primitives: page header, metric group, exception queue, evidence checklist, record context, timeline, status label, action-result panel, empty/error state, search/filter toolbar, version-bound authorization panel.

Feature modules: strategy, marketing, sales, commercial, customers, autopilot, insights, settings. Route files should be thin wrappers around typed feature components; avoid duplicating the shell or business invariants across 73 files.

Existing record routes remain the source of truth for selected entities. Every added route in the manifest is a proposed integration route, not proof of an existing API. Keep IDs and relationships typed. Avoid producing one permanent fictional record per detail page.

## Prototype behaviors versus real implementation

The prototype deliberately uses in-memory state for design review. `approve-quote`, `send-quote`, `accept-quote`, `meeting-outcome`, `contract-handoff`, `milestone`, scheduling and policy actions illustrate expected UI transitions. Production versions require the correct backend mutations, permissions, audit records and observed results. Some prototype buttons save an example or show an explanatory dialog; that is not a production persistence implementation.

Import selection only demonstrates the validation handoff. The prototype does not parse or upload records. Connection dialogs do not initiate OAuth. Login does not authenticate. Customer communication does not send. Readiness and provider badges are illustrative.

The optional `document.modelContext` tools in `app.js` expose only prototype reading/navigation. They are not needed to integrate the design with Next.js and do not supply backend capability.

## Data correctness

Separate opportunity amount, accepted bookings, annual recurring value, one-time activation, taxes and cash collection. The reference quote illustrates an 8% allocation to a ₹12L recurring line and ₹6L one-time line; values are fictional. Use actual contract lines, configured currency and business policy. Do not bake these examples into production calculations.

Mock/provider/example evidence must not silently influence live decisions. Missing input should render unavailable with a useful reason. Record why a handoff is blocked, who owns it, and which fact or decision can unblock it.

## Coverage expectations

All 49 original routes must retain their functionality. The 24 additions include workflow authoring/handoffs, strategy/setup/security, and two design-review utilities. The page index and design system should be development-only unless an administrator explicitly needs them.

Use `SCREEN_MANIFEST.json` to track screen implementation, route, existing source page, suggested Next.js destination and next handoff. Complete the layout even where a backend action must remain disabled due to a documented missing contract.

## Validation boundary

Previous validation covered all 73 screen renderers, 49 source-page mappings, 1,816 internal links and selected demo transitions in a simulated DOM. It did not establish visual browser correctness, real provider execution, authentication or production readiness. Run those checks against the integrated Next.js application.
