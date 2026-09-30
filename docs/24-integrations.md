# Integrations

Never place external SDK logic inside domain services.

```text
EmailProvider
  MockEmailProvider
  GmailProvider
  OutlookProvider
```

Same pattern for advertising, voice, calendar, CRM, support, finance, product usage, company/contact/intent data.

Post-sale providers: `MockProductUsageProvider` is always labeled MOCK and is excluded from the health total. `UnavailableSupportProvider` and `UnavailableFinanceProvider` return NOT_CONFIGURED. They are not silent zeros.

MVP: mock email, mock calendar, mock company/contact data. Live adapters are added when credentials exist and must implement the same interface plus an integration health check.

## Gmail and Google Calendar (batch 2)

Env: `EMAIL_PROVIDER=mock|gmail`, `CALENDAR_PROVIDER=mock|google`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `TOKEN_ENCRYPTION_KEY`.

Connect from `/admin/integrations`. One Google row per tenant user. Scopes are stored; Gmail and Calendar health are shown separately.

Send path: Approval → ActionDispatcher → EmailProvider. Status is PENDING/SENDING/SENT/FAILED/RETRYING. Live + disconnected = Blocked by configuration.

Inbound: Celery `sync_inbound_mail` (60s) reads Gmail history into `provider_inbox_events`, then `email_messages`. `POST /api/v1/webhooks/{provider}` persists first (HMAC `X-Webhook-Signature`). Mock inject: `POST /api/v1/integrations/inbox/simulate`.

Idempotency: `email.send:{tenant}:{approval_id}` and unique `(tenant_id, provider, provider_message_id)`.

## Live discovery, ads, and voice (batch 4)

Process-level env (not per-tenant OAuth):

- `DISCOVERY_PROVIDER=mock|apify` plus `APIFY_API_TOKEN`, `APIFY_ACTOR_ID`, `APIFY_LINKEDIN_PROCESS_TOKEN`
- `LINKEDIN_ADS_MODE=mock|live` plus `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AD_ACCOUNT_ID`
- `META_ADS_MODE=mock|live|sandbox` plus `META_ACCESS_TOKEN` and `META_AD_ACCOUNT_ID`. Sandbox uses `META_SANDBOX_AD_ACCOUNT_ID` and does not serve ads. The Page token is only for organic posts and is not used for ads.
- Organic posts are separate from ads. `LINKEDIN_POSTING_MODE` and `META_POSTING_MODE` are `mock` or `live`. Live without a post token and page id is `NOT_CONFIGURED` and nothing is published. The ads sandbox does not apply to Page or Instagram posts.
- Content drafts use the configured Gemini key. Gemini writes the full post and ad from the company profile and product. An optional note can steer the angle. Already-sent drafts are included in the next prompt so the copy is not repeated. A missing key is `NOT_CONFIGURED` and invents no copy. Publish sends a post through the organic publisher or creates a paused ad. It does not activate spend. Instagram still needs a public image URL. The capture link on the seller profile is copied onto the draft with UTM parameters so a form submit becomes an inbound lead.
- `VOICE_PROVIDER=mock|twilio|vapi` plus Twilio/Vapi vars (`VAPI_ASSISTANT_ID`, `VAPI_PHONE_NUMBER_ID`, `VAPI_WEBHOOK_SECRET`)
- `VOICE_CONVERSATION_PROVIDER=dograh` uses the local Dograh voice agent as the caller. `DOGRAH_API_BASE`, `DOGRAH_API_KEY`, and `DOGRAH_AGENT_UUID` are required. Sales Engine posts the number and the published sales script to Dograh's public agent API. Dograh places the call. Exotel and Twilio are not dialed for that call. A missing key records not configured and does not place a call.

Live mode without credentials is `NOT_CONFIGURED`. Live HTTP failure never swaps to mock.

`POST /api/v1/webhooks/{provider}` authenticates (HMAC, Twilio signature, or Vapi secret), persists `provider_inbox_events`, returns 200, then processes on Celery (inline on SQLite tests). Ads status/metrics sync via `sync_ad_campaigns` every 5 minutes.

Idempotency: `ads.launch:{tenant}:{approval_id}`, `voice.dial:{tenant}:{approval_id}`. Trace and dead letters live in `provider_actions`.
