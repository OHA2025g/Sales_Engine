# Sales Engine — updated code only

This package contains only the changes from the first 73-screen frontend reference to the manual-entry update. It does not include complete replacements for app.js, style.css, index.html, or unchanged data.js/pages.

## Included code

- `forms.js`: the entirely new component/module containing 36 complete entity schemas, sectioned create/edit dialogs, field validation, quote lines/totals, identity linking, record details, browser retention, CSV import, export and settings helpers.
- `existing-files.patch`: only modified lines in `prototype/app.js`, `prototype/index.html`, and `prototype/style.css`. It integrates the new module, replaces generic creation and list/detail behavior, updates routing/actions, and adds form/detail styling. Removed lines show what to replace; added lines are the update. Unchanged screen code is omitted.
- `CHANGE_MANIFEST.json`: exact baseline and updated source checksums.

## Give this instruction to Cursor

Apply only the manual-entry/update changes in this package to the previously supplied Sales Engine redesign. Read `forms.js` and `existing-files.patch`. Preserve the existing dark layout, all 73 screens, and unrelated changes. Do not regenerate the whole application.

If working on the original static reference: the patch assumes the FIRST package, whose design source commit is d69804dd8e2f68799b8d883d1e46cc0eacc3909d. Copy forms.js into its `prototype/` folder. From the reference package root, run `git apply --check --unidiff-zero /path/to/existing-files.patch`, then `git apply --unidiff-zero /path/to/existing-files.patch`. Compare the original file checksums with CHANGE_MANIFEST.json before applying. The index update loads forms.js between data.js and app.js. If the latest full package is already installed, these changes are already included; do not apply twice.

If the design is already ported into the original Next.js website: use this as a change reference, not a patch to Next.js file paths. Port the complete schemas and changed behaviors into the existing React/TypeScript components, real selected-record routes and current APIs. Preserve authentication, tenant isolation, permissions and provider integrations. Every save must retain all entered values and open the correct record; every list must support editing. Keep all optional details, linked context, repeated quote lines and journey steps, validation and unsaved-change protection. CSV imports must preview errors and duplicates before importing valid rows.

The static reference stores structured review records on the browser (or for the current session). Replace that store with the company's existing authorized API persistence in the production application. File controls currently retain metadata only. Configurations, message drafts and schedules do not initiate OAuth, send messages or publish. Use the real backend adapters for those outcomes.

## Verification

The delta was reconstructed against the exact first reference and verified byte-for-byte against the published updated source. Existing verification covers 73 screens, 36 create/edit form types, 44 creation/save entry points, linked identities, reload retention, required/business validation, quote arithmetic and revision reset, CSV import/error exclusion, preferences and persistence opt-out. Browser visual verification was unavailable.
