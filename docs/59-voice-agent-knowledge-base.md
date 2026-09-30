# AGRAYIAN Autonomous Revenue OS — voice agent knowledge base

Use this document as the only product source for a voice agent. Answer in short spoken sentences first, then add detail if the caller asks. If a fact is not in this document, say you do not have it. Do not invent prices, discounts, customer names, revenue numbers, legal terms, or roadmap dates.

Product name: AGRAYIAN Autonomous Revenue OS.
Maker: AGRAYIAN AI Labs.
What it is: a multi-tenant revenue operating system. It is not only a CRM, not only lead management, not only sales automation, and not only an AI SDR.

## How to answer

- Prefer the short answer under each heading, then the facts below it.
- Say “human approval” whenever the action sends money, a message, a call, a quote change, or a contract.
- Say “mock” or “not connected” when a channel has no live credentials. Never describe a mock as a live send.
- Do not quote API keys, passwords, or tokens. This document does not contain them.
- Do not promise that ads will be served. A sandbox ad account never serves ads. A paused campaign does not spend.
- Do not say a machine-learning model is predicting revenue. No production model is trained. Rules score the work. Prediction tasks are collecting data.
- AGRAYIAN’s own subscription price is not in this knowledge base. Do not make one up. The quote tools inside the product price the tenant’s own offers to their buyers.

## One-sentence description

AGRAYIAN Autonomous Revenue OS runs the revenue lifecycle from finding a market through acquisition, selling, closing, onboarding, retention, expansion, and advocacy, with AI doing routine work and humans approving anything that spends money, sends a message, or changes a commercial commitment.

## The lifecycle

The lifecycle is Intelligence, Acquire, Sell, Close, Succeed, Retain, Expand, Advocate, and Learn.

The five questions the product is built to answer:

1. Where should we sell?
2. Who should we sell to?
3. What should we sell?
4. How should we engage?
5. How do we retain and grow the customer?

Every module should help find, acquire, convert, close, deliver, retain, grow, advocate, or learn. The strategic metric is revenue productivity per human, not zero humans.

## Who does what

AI executes routine work and recommends complex work. Humans approve important work and own the relationship.

Humans stay responsible for strategy, high-value relationships, sensitive communication, large commercial approvals, major negotiations, legal decisions, financial commitments, exceptions, governance, and escalations.

Action levels:

- Level 0, read: automatic.
- Level 1, internal write: tenant policy.
- Level 2, external communication: default is approval.
- Level 3, commercial: approval rules.
- Level 4, financial or legal: an explicit human.

Default autonomy:

- Research, lead scoring, internal tasks, and email drafts can run automatically.
- Sending email, placing a voice call, creating a campaign, and changing ad spend require approval.
- Discounts and contract acceptance stay with a human.

The Approval Center is the queue for outbound messages, campaign launches, ad spend, proposal changes, discounts, quotes, and renewal offers. A reviewer can approve, edit, reject, regenerate, assign, or escalate. Feedback is stored.

Autopilot is the operating switch. It reacts to events and a reconcile cycle. “Run now” only speeds the cycle. Autopilot does not auto-approve a dial, an email send, or ad spend.

## What the workspace looks like

The signed-in app is organized like this:

- Start here: Home, Autopilot, Approvals, Leads, and Who we sell to.
- Records: Accounts, Contacts, Import CSV, and Tasks.
- Sell: Pipeline, Campaigns, Social posts, Sequences, and Inbound.
- Meet: Conversations, Meetings, and Voice scripts.
- After the sale: Deal risk, Quotes, Forecast, Customers, Success, Renewals, Expansion, and Advocacy.
- More: Copilot, Knowledge, Market, Playbooks, and Models.
- Admin: Pilot readiness, Integrations, People, Teams, Flags, and Audit.

A person only sees a page when their role has that permission. Permission denied is a real screen, not a hidden error.

## Home and command center

Home is the command center. It shows attention that needs a human, including lifecycle risks, and the state of Autopilot. It does not invent pipeline or revenue numbers. Numbers come from stored records.

## Market intelligence

Short answer: Market answers where to sell, using markets, signals, and triggers. Scores are rules, and mock signals are labeled mock.

The Market area stores markets and signals: account, technology, intent, competitive, and trigger events. Every signal keeps source, evidence, confidence, time, type, the entity it belongs to, impact, and a recommended action.

Rules version one scores market attractiveness, AI readiness, technology readiness, budget potential, growth potential, competitive intensity, procurement probability, and buying timing. Those scores are deterministic. The model does not invent them.

Account research can draft a company overview, priorities, technology, triggers, stakeholders, and which AGRAYIAN solutions fit, but only from tools and retrieved knowledge. If the evidence is missing, it should not fill the gap with a guess.

## Who we sell to

Short answer: Ideal customer profiles and personas define who the tenant sells to. Discovery can search for people only when a live provider is connected. Mock discovery invents nobody.

ICPs and personas live under Who we sell to. Discovery can use a query builder. Live discovery uses a connected provider such as Apify when that mode is on and credentials exist. A daily limit applies. If discovery is live and credentials are missing, the result is not configured, not a fake list of people.

## Leads and inbound

Short answer: Leads can be captured from a public form, imported from CSV, or created in the app. Consent and do-not-contact are checked before any outreach. Uncertain duplicates go to a human.

Inbound capture stores source, channel, campaign, ad, creative, keyword, landing page, UTM parameters, time, consent, and device. Public website capture uses a per-tenant form key and is rate limited. The authenticated capture route still requires the capture permission.

Opt-out and do-not-contact are respected before any external communication.

Dedupe is deterministic on email and domain, plus a fuzzy company-name review. Uncertain merges wait for a person. Phone matching and embedding similarity merges are not in this version.

Lead score version one is out of 100: ICP fit 25, intent 20, engagement 20, persona 10, company potential 10, buying trigger 10, timing 5. The score is rules, not a trained model. The AI can explain a score. It does not invent one.

Enrichment of company or contact data runs only through a configured provider. If that provider is mock or missing, the product does not pretend the enrichment came from a live data vendor.

## Accounts, contacts, and tasks

Accounts are companies. Contacts are people at those companies. Account 360 is meant to show the company, contacts, buying committee, signals, pipeline, activities, contracts, success, renewals, expansion, and AI insights as those records exist.

CSV import creates leads the tenant already has. Tasks are internal work. Creating an internal task can be automatic. Sending that task’s content outside the company is not.

## Pipeline and opportunities

Short answer: Pipeline is the deal board. Stages run from Qualification through Closed Won or Closed Lost. Closed Won creates the customer and the renewal stub so post-sale work can start.

Default stages, in order:

1. Qualification
2. Discovery
3. Solution Fit
4. Technical Discovery
5. Demo
6. Business Case
7. Proposal
8. Commercial Discussion
9. Negotiation
10. Procurement
11. Legal
12. Commit
13. Closed Won
14. Closed Lost

Deal risk, also called the deal coach, is rules version one. It flags a missing buyer, a weak champion, a stall, a close date that slipped, competitor risk, and a missing next step. It explains risk. It does not invent a win probability from a trained model.

Forecast uses stored snapshots of the pipeline. It does not fabricate a forecast number.

## Sequences and conversations

Sequences enroll people into steps. A step that sends email or places a call waits for approval unless a human already approved that action. Conversations are the thread of messages and calls. Inbound mail can be classified when Gmail is connected. A mock inbox can be simulated for tests, and that simulation is not a real customer reply.

## Meetings

Short answer: Meetings can be captured by a bot, by an uploaded recording, or by notes a person types. A bot may not join until recording consent is approved. Insights must cite the transcript or say they cannot tell.

Meeting intelligence is transcript-only. If the transcript does not support a claim, the product abstains. It does not invent what was said.

Uploaded audio can be transcribed when Gemini speech-to-text is configured. If that key is missing, transcription is not configured. It does not return a fake transcript.

## Voice calls

Short answer: There is a gated dialer. Autopilot never approves a call by itself. India calls have extra legal gates.

Telephony and the speaking agent are separate, except when Dograh is the caller. The phone number’s region picks the carrier: numbers starting with +91 use Exotel unless the tenant overrides that. Other numbers use Twilio when Twilio is configured. Vapi, or a human handoff, is who speaks on those carrier calls. When `VOICE_CONVERSATION_PROVIDER` is dograh, Dograh places the call and speaks. The sales script is sent as context. Exotel and Twilio are not dialed for that call. Dograh needs an API base, an API key, and a published agent UUID. If any of those is missing, the call is not configured and nothing is dialed.

A call is blocked unless consent exists, or there is an explicit request plus an approval. India outbound calls also require a clear NDNC or DND check, the time to be between 10:00 and 21:00 India Standard Time, and not on a Sunday, plus recording consent for the announcement. Daily caps, circuit breakers, and idempotency still apply.

Twilio and Vapi can sign their callbacks. Exotel does not. Exotel callbacks are trusted by a secret routing token on the webhook URL and an optional IP allowlist. Do not describe that as a signature.

A mock voice provider never places a call and never invents a transcript. WhatsApp is not connected until a live adapter and credentials exist. Do not say WhatsApp messaging works today.

Voice scripts are versioned talk tracks the agent or the rep can follow. They are not themselves a phone call.

## Campaigns and ads

Short answer: Campaigns can launch paid ads on LinkedIn and Meta only after approval, and only when that network is connected. Mock ads invent no spend. A paused campaign does not spend. A Meta sandbox account does not serve ads.

Paid channels in the product are LinkedIn and Instagram or Meta. Launch goes through Approvals, then the ads provider. If the provider is live and credentials are missing, the result is not configured. A failed live call is never replaced with a pretend success.

The product can create a campaign, an ad set, a creative, and an ad, then pause, activate, and sync status. Metrics that can be stored after a live sync are spend, impressions, clicks, conversions, and the rates CTR, CPC, and CPL. If the network does not return insights, those numbers stay empty. They are not estimated.

Audience sync sends only consented identifiers.

Return on ad spend is closed-won opportunity amount tied to that campaign, divided by the spend stored on the campaign. If spend was not returned, ROAS is not invented.

LinkedIn ads, when live, use a LinkedIn access token and an ad account id. The Marketing API version header in the product is 202609. A real LinkedIn ad account can spend if a campaign is activated. Connectivity tests are created paused on purpose.

Meta ads use a user access token, not the Facebook Page token. The Page token cannot manage the ad account. Modes are mock, live, or sandbox. Sandbox mode uses the sandbox ad account id. Sandbox ads are not delivered and are not a substitute for a billed campaign. The ad account’s minimum daily budget is read from Meta and the requested budget is raised to that minimum when Meta would otherwise reject it. The campaign is still created paused.

Organic posts are not ads. They do not use the ads sandbox.

## Content

Short answer: Content drafts LinkedIn, Facebook, and Instagram posts plus one ad from the company profile and a product description. Gemini writes the full headline, body, and call to action. A short note from the operator is optional. Already-sent drafts are read so the next draft uses a different angle. Nothing is published until a person sends it. The ad is created paused.

The company profile is the seller: name, what you do, who you sell to, website, proof you are willing to claim, and the public lead-capture link. The product needs a written description. If either is missing, generation stops. The model does not invent a price, a discount, a customer count, or a testimonial. A stored list price may be repeated. It may not be changed.

Each draft includes the capture link with UTM source, medium, and campaign so a person who submits the form shows up as an inbound lead. Publishing a post uses the same organic posting path as Social posts. Publishing an ad creates a paused campaign and does not turn it on. A Meta sandbox ad is still not served. Instagram still needs a public image URL before that draft can be published. Gemini does not create or host that image.

If the Gemini key is missing, the drafts fail as not configured. They are not filled with fake marketing copy.

## Social posts

Short answer: Social posts publish ordinary feed posts to a LinkedIn company page, a Facebook Page, or Instagram. They are separate from ads. Mock mode saves the copy and does not publish it.

LinkedIn company posts need a post token with permission to publish as the organization, plus the organization id. A token that can only post as a member cannot publish as the company page. The product posts as the organization urn. Image URLs on LinkedIn posts are ignored by this publisher.

Facebook posts need a Page id and a Page access token with permission to manage posts and read engagement, and the token must be allowed to post as an admin of that Page. A user token that merely lists those permission names can still be refused by the Page feed.

Instagram posts need the same Page token, an Instagram business account id, and a public image URL. Instagram will not publish a text-only post from this product. The flow creates a media container, then publishes it.

If posting mode is live and the token or page id is missing, the post is stored as failed and not configured. Nothing is published.

## Quotes and commercial

Short answer: Quotes use deterministic math. The language model does not invent prices, taxes, or totals. A discount of 10 percent or more waits for approval.

The commercial desk stores products and quotes. A line can be a product, SKU, service, subscription, license, implementation, or support, with quantity, currency, discount, tax, duration, and terms.

Documented discount routing example: under 10 percent can sit with a sales manager, 10 to 20 percent with a director, 20 to 30 percent with a business head, and over 30 percent with the CEO or finance. The implemented gate is that a discount of at least 10 percent enters the Approval Center.

Proposal states run from Draft, Internal Review, Approved, Sent, Viewed, Revised, and Negotiation, to Accepted or Rejected.

Contract fields such as dates, renewal, notice, pricing, and service levels can be extracted for review. That extraction is not legal advice. Accepting a contract is a human decision.

## Customers, success, and health

Short answer: When a deal is Closed Won, the product creates the customer, a handoff pack, an eight-step onboarding plan, a success plan, and a health score. Health counts only live, fresh evidence. Mock usage is excluded.

The handoff pack carries objectives, solution, scope, commercials, stakeholders, risks, and success criteria.

The default onboarding milestones, in order, are Kickoff, Technical setup, Integration, Data preparation, Training, User enablement, Acceptance, and Go-live. Each has an owner role, a due window, and required evidence. An overdue milestone can raise a risk and a next action. If every milestone is done, onboarding can be marked complete.

Health rules version two uses these components and weights: onboarding 12, usage 16, adoption 12, support 12, engagement, commercial, success, and relationship. Only components that are live and fresh enter the score. Usage from the mock provider is labeled mock and is left out of the total. Support and finance stay unavailable until a signed webhook actually delivers them. They are not stored as a fake zero.

Customer risk uses churn rules. The success agent may draft outreach, a meeting brief, or a QBR. Sending still waits in Approvals.

Customer 360 is the post-sale view of that customer’s health, onboarding, risks, and commercial context.

## Renewals

Short answer: Closed Won opens a renewal record. Renewal readiness is rules version two. The product recommends. It does not auto-send a renewal offer.

Renewal windows are tracked. A renewal offer that leaves the building needs approval.

## Expansion

Short answer: Expansion recommends upsell or cross-sell from whitespace. It does not automatically create an opportunity.

A person decides whether a recommendation becomes a deal.

## Advocacy

Short answer: Advocacy rules version two decide whether a customer is eligible to be a reference. Open critical issues or thin evidence block advocacy.

Advocacy covers references, case studies, testimonials, referrals, and partner motions. Eligibility is a score plus evidence. It is not a promise that the customer has agreed to be public.

## Copilot, agents, and knowledge inside the product

Short answer: Copilot answers from tenant data through approved tools. It does not get a direct database login. Knowledge is documents the tenant uploads. Answers must cite those documents or abstain.

The path is person, Copilot, supervisor, a specialist agent, an approved tool, an application service, authorization, then the database.

Specialist agents in the product include a supervisor, knowledge, account research, and lead scoring that explains a score. Other agent names may exist as contracts. They are not extra brains that quietly act.

The in-app Knowledge page is where a tenant uploads files such as playbooks. Those files are parsed, chunked, embedded, and retrieved only inside that tenant. One tenant never sees another tenant’s chunks. This voice-agent document is a product explanation. It is not automatically the tenant’s uploaded knowledge unless someone uploads it there.

Live chat, reasoning, embeddings, and uploaded-meeting transcription use Google Gemini when a Gemini API key and model ids are configured. Model ids come from settings. They are not hardcoded. If the key is missing, the provider is not configured. The product does not silently switch to a fake model and pretend it is Gemini.

Embeddings from Gemini are 3072 numbers long. After changing the embedding model, knowledge must be ingested again or older chunks will not match.

Every completion can record provider, model, agent, prompt version, tokens, latency, and estimated cost.

## Models and learning

Short answer: The product collects features and labels so a model could be trained later. No champion machine-learning model is in production. Rules remain in charge.

Prediction tasks are in data collection. Training is refused until a task is ready for an experiment and a human starts one shadow experiment. Shadow predictions do not replace the rules score. Promoting a model to champion is off.

The Models page is honest about that. It should not be described as a live forecasting AI.

## Playbooks

Playbooks are persisted runs of a revenue motion, not a one-off chat. A run can be inspected after it finishes. Process memory is not how sequences, approvals, or agent runs are stored.

## Integrations desk

Short answer: Admin, then Integrations, is where a tenant connects providers. A connected tenant credential wins over a shared server default. Live without credentials is not connected. It never falls back to mock.

Channels report LIVE, MOCK, or NOT CONNECTED.

What can be connected, and the honest limit:

- Gmail and Google Calendar: OAuth from the integrations desk. Mail send and calendar booking work when that Google account is connected and the scopes include send and calendar events. Inbound Gmail is polled about every 60 seconds. Gmail push via Pub/Sub is not the current path.
- LinkedIn ads: live with an ads token and an ad account id.
- Meta ads: mock, live, or sandbox. Sandbox does not serve ads. The ads token is a user token.
- LinkedIn, Facebook, and Instagram organic posts: separate from ads, mock or live.
- Discovery: mock, or Apify when configured.
- Voice: mock, Twilio, Vapi, Exotel for India, and Dograh as a caller that places the call itself. Each needs its own credentials.
- Meeting capture: manual notes, upload plus transcription, or a Recall bot after recording consent.
- Enrichment: only when an enrichment provider and key are set.
- Usage, support, finance, and ERP: only through signed webhooks. There is no live Zendesk or Stripe screen that invents tickets or invoices.
- WhatsApp: not configured.

Provider failures are recorded. Repeated failures can open a circuit breaker. Dead letters can be inspected. Actions are idempotent so the same approval does not send twice.

## Security and tenancy

Short answer: Every customer’s data is a tenant. A user in one tenant cannot read another tenant’s rows. Changes are audited.

Each tenant-owned row includes a tenant id. Repositories filter by that tenant. Postgres deployments can enforce row-level security.

Permissions are strings such as campaigns.read, not a hardcoded role name inside a domain service. Roles are bundles of those permissions.

Audit records the actor, tenant, action, entity, before and after, whether a human or AI did it, and a correlation id.

Secrets are encrypted at rest with a token encryption key. They are not written into this knowledge base. Production refuses to run as a casual demo: it requires the encryption key, a public HTTPS address for provider callbacks, a metrics token if metrics are exposed, and malware scanning for uploads. Production will not seed demo data unless that is explicitly allowed.

Consent, opt-out, and do-not-contact are checked before external communication.

## Pilot versus production

Short answer: The product can be activated as a controlled pilot. That is not the same as unrestricted enterprise production.

Pilot readiness is an admin page. Activate copies deployment credentials into the tenant when those secrets exist, then stops if critical checks fail. Operating mode is stored on the tenant.

A public HTTPS host is required before Exotel, Twilio, Vapi, Recall, or Gmail callbacks can reach an API that is not on the operator’s own machine.

## What the product will not do

Say these clearly if asked:

- It will not send email, place a call, launch ads, or change a quote without the approval rule for that action.
- It will not invent pipeline, revenue, spend, click-through rate, or a transcript.
- It will not train or silently promote a machine-learning champion. Rules score health, deal risk, lead fit, renewal readiness, and advocacy.
- It will not merge two uncertain leads by itself.
- It will not let a meeting bot join before recording consent.
- It will not dial an India number outside the legal window or when the do-not-call check is not clear.
- It will not treat a Meta sandbox campaign as a live ad that people will see.
- It will not use a Facebook Page token to manage ads.
- It will not publish an Instagram post without a public image.
- It will not give legal advice from a contract extraction.
- It will not auto-create an expansion opportunity.
- It will not answer with another tenant’s data.
- It does not include AGRAYIAN’s own price list in this knowledge base.

## Frequently asked questions

**What is AGRAYIAN Autonomous Revenue OS?**
It is AGRAYIAN AI Labs’ system for running the whole revenue lifecycle, from market and leads through deals, quotes, onboarding, renewal, expansion, and advocacy. AI does routine work. Humans approve money, messages, and commitments.

**Is this a CRM?**
It includes CRM records — leads, accounts, contacts, and a pipeline — and it also runs acquisition, ads, social posts, meetings, voice, quotes, customer success, renewals, expansion, and advocacy. Calling it only a CRM is incomplete.

**Can it send email by itself?**
It can draft email automatically. Sending goes through approval, then Gmail if Google is connected. If mail is in mock mode, the message is not sent.

**Can it call people?**
Yes, through a gated dialer. A call needs consent and approval. India numbers use Exotel and must pass do-not-call and calling-hour checks. The product will not call on its own just because Autopilot is on.

**Can it post on LinkedIn, Facebook, and Instagram?**
Yes, as organic posts, separate from ads. LinkedIn posts go to the company page. Facebook posts go to the Page. Instagram posts need a public image. Mock mode does not publish.

**Can it run ads?**
Yes on LinkedIn when ads mode is live, and on Meta when ads mode is live or sandbox. Launch waits for approval. Sandbox Meta ads are not served. Paused campaigns do not spend. Metrics appear only after the network returns them.

**Does the AI set the price?**
No. Quote totals, discounts, taxes, and dates are calculated by the application. A discount of 10 percent or more needs approval. The language model may explain a quote. It may not invent the numbers.

**How does it know a customer is healthy?**
Health is rules version two. It mixes onboarding, usage, adoption, support, engagement, commercial status, success, and relationship, and only when that evidence is live and fresh. Mock usage is ignored. Missing support or finance data is unavailable, not zero.

**What happens when we win a deal?**
Closed Won creates the customer, a handoff pack, an eight-milestone onboarding plan, a success plan, a health score, and a renewal stub.

**Does it predict who will buy?**
It collects the data for that and can explain rule-based scores. It does not have a trained production model making those predictions.

**Is my data mixed with other companies?**
No. Each customer of AGRAYIAN is a tenant. Queries, knowledge files, and audits are scoped to that tenant.

**What should I open first?**
Home for attention, Approvals for anything waiting on a human, Leads and Pipeline for selling, and Integrations if a channel says it is not connected.

**What is not ready?**
WhatsApp sending, Gmail push notifications, live Zendesk, live Stripe, and a trained forecasting model. Say they are not available yet rather than describing a workaround that does not exist.
