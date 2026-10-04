# Sales Engine — complete 73-screen frontend source

This package contains the full source of the dark redesigned Sales Engine prototype and instructions for implementing it in the existing `OHA2025g/Sales_Engine` website.

## Use with Cursor

1. Extract this ZIP inside your repository into a reference folder, for example `design-reference/Sales_Engine_Frontend_73_Screens/`.
2. Open your existing Sales_Engine repository in Cursor.
3. Read `CURSOR_IMPLEMENTATION_PROMPT.md` and paste its contents into Cursor Agent. Adjust the reference folder path if you used a different location.
4. Ask Cursor to implement the redesign across the entire page manifest, retaining your existing authentication, permissions, API integration, and working features.

Do not replace the existing Next.js application with the standalone prototype. Its HTML/CSS/JavaScript defines the design and interactions to port into React/TypeScript components and real routes.

## What is included

| File / folder | Contents |
|---|---|
| `prototype/index.html` | Original document, app container, dialog, metadata, favicon |
| `prototype/style.css` | Complete dark theme, component styling, responsive behavior |
| `prototype/data.js` | All 73 screens, nine workspace definitions, fictional datasets |
| `prototype/app.js` | Every screen renderer and prototype interaction |
| `preview/sales-engine-all-73-screens.html` | All frontend code embedded in one HTML file; open it directly |
| `FULL_FRONTEND_CODE.md` | All four source files reproduced in one text file for AI ingestion |
| `CURSOR_IMPLEMENTATION_PROMPT.md` | Implementation instructions for your existing Next.js project |
| `docs/SCREEN_MANIFEST.json` | Complete screen registry, existing source pages, proposed routes |
| `docs/ROUTE_MAPPING.csv` | Easy-to-review page coverage and route mapping |
| `docs/DESIGN_TOKENS.json` | Theme and component color tokens extracted from the source |
| `docs/UI_UX_HANDOFF.md` | Design system, role views, flows, component states, implementation requirements |
| `docs/REPOSITORY_AUDIT.md` | Earlier source-backed gap audit and workflow architecture |
| `docs/INTEGRATION_NOTES.md` | Existing stack, source-to-React mapping, API and state boundaries |
| `docs/VALIDATION_RESULTS.json` | Page coverage and demonstration checks from the design pass |
| `CHECKSUMS_SHA256.json` | Integrity hashes for all supplied files |

## Preview

Open `preview/sales-engine-all-73-screens.html`. Use **All page designs** or command search to navigate the complete product. All HTML, CSS and JavaScript are embedded; the optional Inter font loads from Google Fonts, with system-font fallback offline.

You can also serve `prototype/` with any static web server. Python example, run from this package folder:

```bash
python -m http.server 8080 --directory prototype
```

Then open `http://localhost:8080/`.

## Important implementation boundary

This is the complete frontend source of the delivered **prototype**, not a pre-integrated Next.js production frontend. Records, metrics, role changes, approvals, sends, schedules, and other outcomes are illustrative. They do not call real APIs or providers. Cursor must preserve the existing live integrations and replace demonstration state with real API data and server-authorized mutations.

The code covers 49 existing page templates and 24 additional workflow/design screens. The prototype's page index and design-system review utilities should be development-only in production unless explicitly required.

Reference design source commit: `d69804dd8e2f68799b8d883d1e46cc0eacc3909d`.
Reference audited application commit: `fa4bc3453cad8c6a7e67fcee3d5c6a2e6b65a1d9`.
