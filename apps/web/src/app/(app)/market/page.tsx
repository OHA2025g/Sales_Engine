"use client";

import { Checks, Go, initials, Line, Panel, Stats } from "@/components/ds";
import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { Button, Drawer, Field, FormActions, Input, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import type { Market } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";

type Overview = { markets: number; signals: number; triggers: number; mock_signals: number; scored_markets: number };

export default function MarketPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const form = useForm({ defaultValues: { name: "", industry: "", geography: "", description: "" } });
  const overview = useQuery({
    queryKey: ["market-overview"],
    queryFn: async () => (await api<Overview>("/api/v1/market/overview")).data,
    enabled: can("markets.read"),
  });
  const query = useQuery({
    queryKey: ["markets"],
    queryFn: async () => (await api<Market[]>("/api/v1/market")).data ?? [],
    enabled: can("markets.read"),
  });
  const create = useMutation({
    mutationFn: (body: { name: string; industry: string; geography: string; description: string }) =>
      api("/api/v1/market", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["markets"] });
      void client.invalidateQueries({ queryKey: ["market-overview"] });
      setOpen(false);
      form.reset();
    },
  });
  const refresh = useMutation({
    mutationFn: () => api("/api/v1/market/refresh", { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["market-overview"] });
    },
  });

  if (!can("markets.read")) return <DeniedState />;
  if (query.isLoading || overview.isLoading) return <LoadingState label="Reading the market floor" />;
  if (query.isError || overview.isError) return <ErrorState message="Market intelligence could not be assembled." />;
  const rows = query.data ?? [];
  const k = overview.data;

  return (
    <div>
      <PageHeader
        eyebrow="Phase 7"
        title="Market Intelligence"
        subtitle="Attractiveness and timing are scored in code. Providers are labeled mock until a live vendor is configured."
        actions={
          <>
            <Link href="/market/signals" className="text-sm text-brand">Signals</Link>
            <Link href="/market/triggers" className="text-sm text-brand">Triggers</Link>
            {can("signals.write") ? (
              <Button variant="line" onClick={() => refresh.mutate()}>
                {refresh.isPending ? "Refreshing…" : "Refresh mock providers"}
              </Button>
            ) : null}
            {can("markets.write") ? <Button onClick={() => setOpen(true)}>Define a market</Button> : null}
          </>
        }
      />
      <Stats
        items={[
          { name: "Accounts monitored", value: String(k?.markets ?? "—"), note: "Defined markets in this tenant" },
          { name: "Fresh relevant signals", value: String(k?.signals ?? "—"), note: `${k?.mock_signals ?? 0} labeled mock` },
          { name: "Buying hypotheses", value: String(k?.scored_markets ?? "—"), note: "Scored with rules-v1" },
          { name: "Sources requiring attention", value: String(k?.triggers ?? "—"), note: "Signal triggers" },
        ]}
      />
      <div className="ds-grid wide">
        <Panel
          title="Prioritized account opportunities"
          extra={<Go href="/market/signals">All signals</Go>}
          body={false}
        >
          {rows.length === 0 ? (
            <div className="empty">
              <h3>No markets yet</h3>
              <p>Define a thesis. Scores stay at zero until signals exist.</p>
            </div>
          ) : (
            rows.map((row) => (
              <div className="row" key={row.id}>
                <span className="avatar square">{initials(row.name)}</span>
                <div className="main">
                  <h3>{row.name}</h3>
                  <p>{row.description || `${row.industry || "Industry not set"} · ${row.geography || "Geography not set"}`}</p>
                  <div className="ds-flex" style={{ marginTop: 8 }}>
                    <span className="tag purple">Attractiveness {row.attractiveness}</span>
                    <span className="tag">Timing {row.buying_timing}</span>
                  </div>
                </div>
                <Go href={`/market/${row.id}`}>Inspect brief</Go>
              </div>
            ))
          )}
        </Panel>
        <Panel title="Source and decision quality">
          <Line label="Public company news" value="Verified when a live source is connected" />
          <Line label="Company announcements" value="Verified when a live source is connected" />
          <Line label="Customer usage" value="Production telemetry when connected" />
          <Line label="Contact discovery" value="Eligibility still required" />
          <Line label="Demonstration sources" value="Excluded from live decisions" />
          <hr className="rule" />
          <Checks
            items={[
              { label: "Evidence relevance is visible", ok: (k?.signals ?? 0) > 0 },
              { label: "Mock sources are labeled", ok: true },
              { label: "A permitted journey is attached", ok: false },
            ]}
          />
          <div style={{ marginTop: 16 }}>
            <Go href="/admin/integrations">Manage connections</Go>
          </div>
        </Panel>
      </div>
      <Drawer open={open} title="Define a market" onClose={() => setOpen(false)}>
        <form onSubmit={form.handleSubmit((values) => create.mutate(values))} className="space-y-4">
          <Field label="Name"><Input {...form.register("name", { required: true })} /></Field>
          <Field label="Industry"><Input {...form.register("industry")} /></Field>
          <Field label="Geography"><Input {...form.register("geography")} /></Field>
          <Field label="Description"><Textarea rows={4} {...form.register("description")} /></Field>
          <FormActions pending={create.isPending} onCancel={() => setOpen(false)} label="Create and score" />
        </form>
      </Drawer>
    </div>
  );
}
