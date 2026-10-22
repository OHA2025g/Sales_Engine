# Website signals

Additive reader for public website facts. It does not change discovery, sequences, approvals, or sending.

A tenant confirms signals from a fixed catalog. The free reader then fetches an account's public homepage, `robots.txt`, `sitemap.xml`, and the team, careers, or contact page when a confirmed signal needs it. Private and local addresses are refused. A cohort is the accounts whose newest observation for each chosen signal is actually true. The opening line repeats one of those facts and is not written by a model.

Signals that need paid search, a registry, or an email verifier stay in the catalog and are not collected here.

API:

- `GET /api/v1/site-signals`
- `POST /api/v1/site-signals/status`
- `POST /api/v1/site-signals/profile`
- `POST /api/v1/site-signals/cohort`

Reading uses `signals.read`. Confirming and profiling use `signals.write`.
