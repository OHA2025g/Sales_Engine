"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { MetricStrip } from "@/components/workspace-ui";
import { Badge, Button, Field, Input, Select } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import type { ProviderHealth } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

const CREDENTIAL_PROVIDERS = [
  { value: "linkedin", label: "LinkedIn" },
  { value: "meta", label: "Meta" },
  { value: "twilio", label: "Twilio" },
  { value: "vapi", label: "Vapi" },
  { value: "dograh", label: "Dograh" },
  { value: "apify", label: "Apify" },
  { value: "exotel", label: "Exotel" },
  { value: "gemini", label: "Gemini" },
  { value: "recall", label: "Recall" },
  { value: "enrichment", label: "Enrichment" },
];

const CHANNEL_GROUPS = [
  { title: "Mail and calendar", names: ["Gmail", "Google Calendar"] },
  { title: "Discovery", names: ["Apify", "Gemini"] },
  { title: "Advertising", names: ["LinkedIn Ads", "Meta Ads"] },
  { title: "Voice", names: ["Voice"] },
] as const;

const PROVIDER_LABELS: Record<string, string> = {
  google: "Google",
  linkedin: "LinkedIn",
  meta: "Meta",
  apify: "Apify",
  gemini: "Gemini",
  twilio: "Twilio",
  vapi: "Vapi",
  dograh: "Dograh",
  exotel: "Exotel",
  recall: "Recall",
  enrichment: "Enrichment",
};

type IntegrationAccount = {
  id: string;
  provider: string;
  provider_account_id: string;
  connected_user_id?: string | null;
  account_key?: string;
  status: string;
  scopes: string[];
  capabilities: { gmail?: boolean; calendar?: boolean };
  last_sync_at: string | null;
  last_success_at: string | null;
  last_failure_at?: string | null;
  last_error: string;
};

type Connector = {
  provider: string;
  name: string;
  state: string;
  live_enabled: boolean;
  webhook_url: string;
  last_sync_at: string | null;
  connected_customers: number;
  stale_customers: number;
  failed_syncs: number;
  last_error: string;
};

type EntityMapping = {
  id: string;
  provider: string;
  entity_type: string;
  external_id: string;
  internal_entity_type: string;
  internal_entity_id: string;
  status: string;
  confidence: number;
};

type ChannelFact = {
  mode: string;
  reason: string;
  uses_deployment_default: boolean;
  tenant_credential: boolean;
};

type ChannelsPayload = {
  channels: Record<string, ChannelFact>;
  google: { oauth_ready: boolean; mail: boolean; calendar: boolean };
  posting: Record<string, boolean | string>;
  signals: Record<string, boolean>;
};

type Fact = { label: string; value: string };
type FactGroup = { heading: string; facts: Fact[] };
type Selection =
  | { kind: "channel"; name: string }
  | { kind: "connector"; provider: string }
  | { kind: "account"; id: string };
type DetailTone = "ok" | "gold" | "rose";
type DetailView = { title: string; badge: string; tone: DetailTone; groups: FactGroup[] };

const CHANNEL_LINKS: Record<string, { channels: string[]; posting: string[]; accounts: string[] }> = {
  Gemini: { channels: ["gemini"], posting: ["gemini"], accounts: ["gemini"] },
  Apify: { channels: ["discovery"], posting: ["discovery"], accounts: ["apify"] },
  Gmail: { channels: ["email"], posting: [], accounts: ["google"] },
  "Google Calendar": { channels: ["calendar"], posting: [], accounts: ["google"] },
  "LinkedIn Ads": { channels: ["linkedin"], posting: ["linkedin_ads", "linkedin"], accounts: ["linkedin"] },
  "Meta Ads": { channels: ["meta"], posting: ["meta_ads", "meta_ads_mode", "meta_page", "instagram"], accounts: ["meta"] },
  Voice: {
    channels: ["twilio", "vapi", "dograh", "exotel"],
    posting: ["voice_widget", "voice_agent"],
    accounts: ["twilio", "vapi", "dograh", "exotel"],
  },
};

function shown(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function when(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function toneFor(label: string): DetailTone {
  if (label === "LIVE" || label === "connected" || label === "CONNECTED") return "ok";
  if (label === "MOCK") return "gold";
  return "rose";
}

function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

function accountTitle(row: IntegrationAccount): string {
  const id = row.provider_account_id.trim();
  if (!id || id === "None" || id === "null") return "No account id stored";
  return id;
}

function groupedAccounts(rows: IntegrationAccount[]): { provider: string; label: string; rows: IntegrationAccount[] }[] {
  const order = Object.keys(PROVIDER_LABELS);
  const groups = new Map<string, IntegrationAccount[]>();
  for (const row of rows) {
    const list = groups.get(row.provider) ?? [];
    list.push(row);
    groups.set(row.provider, list);
  }
  return [...groups.keys()]
    .sort((left, right) => {
      const leftIndex = order.indexOf(left);
      const rightIndex = order.indexOf(right);
      return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex);
    })
    .map((provider) => ({ provider, label: providerLabel(provider), rows: groups.get(provider) ?? [] }));
}

function accountFacts(row: IntegrationAccount): Fact[] {
  return [
    { label: "Provider", value: shown(row.provider) },
    { label: "Account", value: shown(row.provider_account_id) },
    { label: "Account key", value: shown(row.account_key) },
    { label: "Status", value: shown(row.status) },
    { label: "Connected user", value: shown(row.connected_user_id) },
    { label: "Gmail", value: shown(row.capabilities.gmail) },
    { label: "Calendar", value: shown(row.capabilities.calendar) },
    { label: "Last sync", value: when(row.last_sync_at) },
    { label: "Last success", value: when(row.last_success_at) },
    { label: "Last failure", value: when(row.last_failure_at) },
    { label: "Last error", value: shown(row.last_error) },
    { label: "Scopes", value: row.scopes.length ? row.scopes.join(", ") : "—" },
  ];
}

function healthFacts(row: ProviderHealth): Fact[] {
  return [
    { label: "Provider", value: shown(row.provider) },
    { label: "Mode", value: shown(row.mode || row.state) },
    { label: "State", value: shown(row.state) },
    { label: "Connected", value: shown(row.connected) },
    { label: "Mock", value: shown(row.is_mock) },
    { label: "Reason", value: shown(row.reason) },
    { label: "Last success", value: when(row.last_success_at) },
    { label: "Last failure", value: when(row.last_failure_at) },
    { label: "Last error", value: shown(row.last_error_summary) },
    { label: "Pending actions", value: shown(row.pending_actions ?? 0) },
    { label: "Failed actions", value: shown(row.failed_actions ?? 0) },
  ];
}

function modeFacts(mode: ChannelFact | undefined): Fact[] {
  if (!mode) return [{ label: "Record", value: "No channel record" }];
  return [
    { label: "Mode", value: shown(mode.mode) },
    { label: "Reason", value: shown(mode.reason) },
    { label: "Workspace credential", value: shown(mode.tenant_credential) },
    { label: "Deployment default", value: shown(mode.uses_deployment_default) },
  ];
}

function describeSelection(
  selected: Selection,
  providerRows: ProviderHealth[],
  connectorRows: Connector[],
  accountRows: IntegrationAccount[],
  channels: ChannelsPayload | undefined,
): DetailView | null {
  switch (selected.kind) {
    case "channel": {
      const row = providerRows.find((item) => item.name === selected.name);
      if (!row) return null;
      const link = CHANNEL_LINKS[row.name] ?? { channels: [], posting: [], accounts: [row.provider] };
      const groups: FactGroup[] = [{ heading: "Status", facts: healthFacts(row) }];
      for (const key of link.channels) {
        groups.push({ heading: `Channel · ${key}`, facts: modeFacts(channels?.channels[key]) });
      }
      if (row.name === "Gmail" || row.name === "Google Calendar") {
        groups.push({
          heading: "Google authorization",
          facts: [
            { label: "OAuth ready", value: shown(channels?.google.oauth_ready) },
            { label: "Mailbox granted", value: shown(channels?.google.mail) },
            { label: "Calendar granted", value: shown(channels?.google.calendar) },
          ],
        });
      }
      const posting = link.posting
        .filter((key) => channels?.posting && key in channels.posting)
        .map((key) => ({ label: key.replaceAll("_", " "), value: shown(channels?.posting[key]) }));
      if (posting.length) groups.push({ heading: "Deployment", facts: posting });
      const stored = accountRows.filter((account) => link.accounts.includes(account.provider));
      if (stored.length === 0) {
        groups.push({ heading: "Stored account", facts: [{ label: "Record", value: "No stored account" }] });
      } else {
        stored.forEach((account, index) => {
          groups.push({
            heading: stored.length > 1 ? `Stored account ${index + 1}` : "Stored account",
            facts: accountFacts(account),
          });
        });
      }
      const badge = row.mode || row.state;
      return { title: row.name, badge, tone: toneFor(badge), groups };
    }
    case "connector": {
      const row = connectorRows.find((item) => item.provider === selected.provider);
      if (!row) return null;
      const health = providerRows.find((item) => item.name === row.name);
      const groups: FactGroup[] = [
        {
          heading: "Connector",
          facts: [
            { label: "Provider", value: shown(row.provider) },
            { label: "State", value: shown(row.state) },
            { label: "Live enabled", value: shown(row.live_enabled) },
            { label: "Webhook", value: shown(row.webhook_url) },
            { label: "Last sync", value: when(row.last_sync_at) },
            { label: "Connected customers", value: shown(row.connected_customers) },
            { label: "Stale customers", value: shown(row.stale_customers) },
            { label: "Failed syncs", value: shown(row.failed_syncs) },
            { label: "Last error", value: shown(row.last_error) },
          ],
        },
      ];
      if (channels?.signals && row.provider in channels.signals) {
        groups.push({
          heading: "Signal",
          facts: [{ label: "Live ingest", value: shown(channels.signals[row.provider]) }],
        });
      }
      if (health) groups.push({ heading: "Provider health", facts: healthFacts(health) });
      return { title: row.name, badge: row.state, tone: toneFor(row.state), groups };
    }
    case "account": {
      const row = accountRows.find((item) => item.id === selected.id);
      if (!row) return null;
      return {
        title: row.provider_account_id || row.provider,
        badge: row.status,
        tone: toneFor(row.status),
        groups: [{ heading: "Account", facts: accountFacts(row) }],
      };
    }
    default: {
      const unexpected: never = selected;
      throw new Error(`Unhandled connection ${JSON.stringify(unexpected)}`);
    }
  }
}

function ConnectionDialog({ detail, onClose }: { detail: DetailView; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="connection-detail-title" data-testid="connection-details">
      <button type="button" className="modal-scrim" aria-label="Close details" onClick={onClose} />
      <div className="modal-card" style={{ maxHeight: "min(760px, calc(100vh - 48px))", overflow: "auto" }}>
        <header className="modal-head">
          <h2 id="connection-detail-title">{detail.title}</h2>
          <Badge tone={detail.tone}>{detail.badge}</Badge>
        </header>
        <div className="modal-body">
          {detail.groups.map((group) => (
            <section key={group.heading}>
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{group.heading}</p>
              {group.facts.map((fact) => (
                <div className="line-item" key={`${group.heading}-${fact.label}`}>
                  <span>{fact.label}</span>
                  <span className="max-w-[60%] break-all text-right">{fact.value}</span>
                </div>
              ))}
            </section>
          ))}
        </div>
        <footer className="modal-foot">
          <Button variant="line" onClick={onClose}>
            Close
          </Button>
        </footer>
      </div>
    </div>
  );
}

function IntegrationsBody() {
  const { can } = useAuth();
  const client = useQueryClient();
  const params = useSearchParams();
  const query = useQuery({
    queryKey: ["integrations"],
    queryFn: async () => (await api<IntegrationAccount[]>("/api/v1/integrations")).data ?? [],
    enabled: can("integrations.read"),
    refetchInterval: 5000,
  });
  const providers = useQuery({
    queryKey: ["integration-providers"],
    queryFn: async () => (await api<ProviderHealth[]>("/api/v1/integrations/providers")).data ?? [],
    enabled: can("integrations.read"),
    refetchInterval: 5000,
  });
  const connectors = useQuery({
    queryKey: ["integration-connectors"],
    queryFn: async () => (await api<Connector[]>("/api/v1/integrations/connectors")).data ?? [],
    enabled: can("integrations.read"),
    refetchInterval: 5000,
  });
  const mappings = useQuery({
    queryKey: ["entity-mappings"],
    queryFn: async () => (await api<EntityMapping[]>("/api/v1/integrations/mappings")).data ?? [],
    enabled: can("integrations.read"),
    refetchInterval: 5000,
  });
  const channels = useQuery({
    queryKey: ["integration-channels"],
    queryFn: async () => (await api<ChannelsPayload>("/api/v1/integrations/channels")).data,
    enabled: can("integrations.read"),
    refetchInterval: 5000,
  });
  const [selected, setSelected] = useState<Selection | null>(null);
  const closeDetails = useCallback(() => setSelected(null), []);
  const [changeTargets, setChangeTargets] = useState<Record<string, string>>({});
  const [credProvider, setCredProvider] = useState("linkedin");
  const [credToken, setCredToken] = useState("");
  const [credExtra, setCredExtra] = useState("");
  const confirmMapping = useMutation({
    mutationFn: (id: string) => api(`/api/v1/integrations/mappings/${id}/confirm`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["entity-mappings"] }),
  });
  const ignoreMapping = useMutation({
    mutationFn: (id: string) => api(`/api/v1/integrations/mappings/${id}/ignore`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["entity-mappings"] }),
  });
  const changeMapping = useMutation({
    mutationFn: ({ id, internal_entity_id }: { id: string; internal_entity_id: string }) =>
      api(`/api/v1/integrations/mappings/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ internal_entity_type: "customer", internal_entity_id }),
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["entity-mappings"] }),
  });
  const connect = useMutation({
    mutationFn: async () =>
      (await api<{ authorization_url: string; configured: boolean }>("/api/v1/integrations/google/connect")).data,
    onSuccess: (data) => {
      if (data?.authorization_url) window.location.href = data.authorization_url;
    },
  });
  const disconnect = useMutation({
    mutationFn: (id: string) => api(`/api/v1/integrations/${id}`, { method: "DELETE" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["integrations"] }),
  });
  const unlinkMapping = useMutation({
    mutationFn: (id: string) => api(`/api/v1/integrations/mappings/${id}/unlink`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["entity-mappings"] }),
  });
  const saveCredential = useMutation({
    mutationFn: () =>
      api("/api/v1/integrations/credentials", {
        method: "POST",
        body: JSON.stringify({
          provider: credProvider,
          access_token: credToken,
          extra: credExtra.trim() ? JSON.parse(credExtra) : {},
        }),
      }),
    onSuccess: () => {
      setCredToken("");
      setCredExtra("");
      void client.invalidateQueries({ queryKey: ["integrations"] });
      void client.invalidateQueries({ queryKey: ["integration-providers"] });
    },
  });
  const provision = useMutation({
    mutationFn: () => api("/api/v1/integrations/provision-defaults", { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["integrations"] });
      void client.invalidateQueries({ queryKey: ["integration-providers"] });
    },
  });

  if (!can("integrations.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Reading integrations" />;
  if (query.isError) return <ErrorState message="Integrations could not be assembled." />;
  const rows = query.data ?? [];
  const channelNames: string[] = CHANNEL_GROUPS.flatMap((group) => [...group.names]);
  const channelRows = (providers.data ?? []).filter((row) => channelNames.includes(row.name));
  const google = rows.find((row) => row.provider === "google");
  const notice = params.get("connected") === "google" ? "Google is connected." : params.get("error") ? "Google OAuth did not complete." : "";
  const detail = selected
    ? describeSelection(selected, providers.data ?? [], connectors.data ?? [], rows, channels.data ?? undefined)
    : null;

  return (
    <div>
      <PageHeader
        eyebrow="House"
        title="Integrations"
        subtitle="Google OAuth is per user. Usage, support, finance, and ERP ingest through signed webhooks. Tokens never appear in this desk."
        actions={
          can("integrations.write") ? (
            <Button onClick={() => connect.mutate()} disabled={connect.isPending}>
              {google?.status === "connected" ? "Reconnect Google" : "Connect Google"}
            </Button>
          ) : null
        }
      />
      {notice ? <p className="mb-4 text-sm text-navy">{notice}</p> : null}
      {connect.isError ? <p className="mb-4 text-sm text-[#e08b7a]">Google is not configured on the API.</p> : null}
      <div className="stack">
        <MetricStrip
          items={[
            {
              label: "Live channels",
              value: String(channelRows.filter((row) => (row.mode || row.state) === "LIVE").length),
            },
            {
              label: "Mock channels",
              value: String(channelRows.filter((row) => (row.mode || row.state) === "MOCK").length),
            },
            {
              label: "Signals waiting",
              value: String((connectors.data ?? []).filter((row) => row.state !== "LIVE").length),
            },
            { label: "Stored accounts", value: String(rows.length) },
          ]}
        />
        {channelRows.length ? (
          <div className="stack" data-testid="provider-modes">
            {CHANNEL_GROUPS.map((group) => {
              const items = group.names
                .map((name) => channelRows.find((row) => row.name === name))
                .filter((row): row is ProviderHealth => Boolean(row));
              if (!items.length) return null;
              return (
                <section className="panel" key={group.title}>
                  <header className="panel-head">
                    <h2>{group.title}</h2>
                  </header>
                  <ul className="grid gap-3 p-4 md:grid-cols-2">
                    {items.map((row) => (
                      <li key={row.name}>
                        <button
                          type="button"
                          className="connection-card panel p-4"
                          data-testid={`integration-${row.name.toLowerCase().replaceAll(" ", "-")}`}
                          aria-haspopup="dialog"
                          onClick={() => setSelected({ kind: "channel", name: row.name })}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <p className="text-sm font-semibold text-navy">{row.name}</p>
                            <Badge tone={row.mode === "LIVE" ? "ok" : row.mode === "MOCK" ? "gold" : "rose"}>{row.mode || row.state}</Badge>
                          </div>
                          <p className="connection-note mt-2 text-xs text-[var(--muted)]">{row.reason}</p>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        ) : null}
        {connectors.data?.length ? (
          <section className="panel" data-testid="signal-connectors">
            <header className="panel-head">
              <h2>Customer intelligence</h2>
            </header>
            <ul className="grid gap-3 p-4 md:grid-cols-2">
              {connectors.data.map((row) => (
                <li key={row.provider}>
                  <button
                    type="button"
                    className="connection-card panel p-4"
                    data-testid={`connector-${row.provider}`}
                    aria-haspopup="dialog"
                    onClick={() => setSelected({ kind: "connector", provider: row.provider })}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm font-semibold text-navy">{row.name}</p>
                      <Badge tone={row.state === "LIVE" ? "ok" : "rose"}>{row.state === "NOT_CONNECTED" ? "Not connected" : row.state}</Badge>
                    </div>
                    <p className="mt-2 text-xs text-[var(--muted)]">
                      {row.connected_customers} customers · {row.stale_customers} stale · {row.failed_syncs} failed syncs
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      {mappings.data?.length ? (
        <section className="panel" data-testid="entity-mappings">
          <header className="panel-head">
            <h2>Entity mapping review</h2>
          </header>
          <ul>
            {mappings.data.map((row) => (
              <li key={row.id} className="row" data-testid={`mapping-${row.id}`}>
                <div className="main">
                <p className="text-sm font-medium text-navy">
                  {row.provider} {row.entity_type} {row.external_id}
                </p>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  {row.status} · {row.internal_entity_type} {row.internal_entity_id || "unmapped"} · confidence {row.confidence}
                </p>
                {can("integrations.write") && (row.status === "confirmed" || row.status === "mapped") ? (
                  <div className="mt-3">
                    <Button variant="line" data-testid={`unlink-${row.id}`} onClick={() => unlinkMapping.mutate(row.id)}>
                      Unlink and recalc
                    </Button>
                  </div>
                ) : null}
                {can("integrations.write") && row.status === "pending" ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Button onClick={() => confirmMapping.mutate(row.id)} disabled={confirmMapping.isPending}>
                      Confirm
                    </Button>
                    <Button variant="line" onClick={() => ignoreMapping.mutate(row.id)} disabled={ignoreMapping.isPending}>
                      Ignore
                    </Button>
                    <input
                      className="min-w-[12rem] flex-1 rounded-md border border-[var(--line)] bg-[#101722] px-2 py-1 text-xs"
                      placeholder="Customer id to change"
                      value={changeTargets[row.id] ?? ""}
                      onChange={(event) => setChangeTargets((current) => ({ ...current, [row.id]: event.target.value }))}
                    />
                    <Button
                      variant="line"
                      onClick={() =>
                        changeMapping.mutate({ id: row.id, internal_entity_id: (changeTargets[row.id] || row.internal_entity_id).trim() })
                      }
                      disabled={changeMapping.isPending || !(changeTargets[row.id] || row.internal_entity_id)}
                    >
                      Change
                    </Button>
                  </div>
                ) : null}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section className="panel">
        <header className="panel-head">
          <h2>Stored accounts</h2>
        </header>
        {rows.length === 0 ? (
          <EmptyState
            title="No stored accounts"
            body="Connect Google to send live mail and book meetings. Other channels stay labeled until a credential is saved."
          />
        ) : (
          groupedAccounts(rows).map((group) => (
            <div key={group.provider}>
              <p className="px-5 pt-4 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{group.label}</p>
              <ul>
                {group.rows.map((row) => (
                  <li key={row.id} className="row">
                    <button
                      type="button"
                      className="connection-card main"
                      aria-haspopup="dialog"
                      onClick={() => setSelected({ kind: "account", id: row.id })}
                    >
                      <h3>{accountTitle(row)}</h3>
                      <p className="text-xs text-[var(--muted)]">
                        Last sync {row.last_sync_at ? new Date(row.last_sync_at).toLocaleString() : "never"}
                        {row.provider === "google"
                          ? ` · Gmail ${row.capabilities.gmail ? "ready" : "missing"} · Calendar ${row.capabilities.calendar ? "ready" : "missing"}`
                          : ""}
                      </p>
                      {row.last_error ? <p className="connection-note connection-error">{row.last_error}</p> : null}
                    </button>
                    <div className="row-actions">
                      <Badge tone={row.status === "connected" ? "ok" : "rose"}>{row.status}</Badge>
                      {can("integrations.write") ? (
                        <Button variant="line" onClick={() => disconnect.mutate(row.id)} disabled={disconnect.isPending}>
                          Disconnect
                        </Button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </section>
      {can("integrations.write") ? (
        <section className="panel" data-testid="provider-credentials">
          <header className="panel-head">
            <h2>Workspace credentials</h2>
          </header>
          <div className="panel-body">
            <div className="form-grid">
              <Field label="Provider">
                <Select aria-label="Credential provider" value={credProvider} onChange={(event) => setCredProvider(event.target.value)}>
                  {CREDENTIAL_PROVIDERS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Access token">
                <Input value={credToken} onChange={(event) => setCredToken(event.target.value)} placeholder="Paste the token" />
              </Field>
              <div className="md:col-span-2">
                <Field label="Extra JSON">
                  <Input
                    value={credExtra}
                    onChange={(event) => setCredExtra(event.target.value)}
                    placeholder='Optional. Dograh: {"agent_uuid":"...","api_base":"http://host:port"}'
                  />
                </Field>
              </div>
            </div>
            {saveCredential.isError ? <p className="mt-3 text-sm text-[#e08b7a]">The credential was not saved. Check the token and extra JSON.</p> : null}
            <div className="sticky-action">
              <Button variant="line" onClick={() => provision.mutate()} disabled={provision.isPending}>
                Copy deployment secrets
              </Button>
              <Button onClick={() => saveCredential.mutate()} disabled={saveCredential.isPending || !credToken}>
                Save encrypted
              </Button>
            </div>
          </div>
        </section>
      ) : null}
      </div>
      {detail ? <ConnectionDialog detail={detail} onClose={closeDetails} /> : null}
    </div>
  );
}

export default function IntegrationsPage() {
  return (
    <Suspense fallback={<LoadingState label="Reading integrations" />}>
      <IntegrationsBody />
    </Suspense>
  );
}
