"use client";

import { Checks, Go, Line, Panel, Stats } from "@/components/ds";
import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { labelize, money } from "@/lib/format";
import type { Campaign } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

export default function CampaignWorkspacePage() {
  const params = useParams<{ id: string }>();
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["campaign", params.id],
    queryFn: async () => (await api<Campaign>(`/api/v1/lifecycle/campaigns/${params.id}`)).data,
    enabled: can("campaigns.read"),
  });
  if (!can("campaigns.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Opening the campaign" />;
  if (query.isError || !query.data) return <ErrorState message="This campaign is not in the tenant." />;
  const row = query.data;
  return (
    <div>
      <PageHeader
        eyebrow="Marketing"
        title={row.name}
        subtitle={`${labelize(row.channel)} · ${row.objective || "No objective recorded"}`}
        nextHref="/content"
        nextLabel="Content studio"
      />
      <Stats
        items={[
          { name: "Approved budget", value: money(row.budget), note: "Monthly ceiling from the plan" },
          { name: "Recorded spend", value: money(row.spent), note: "Separate from product price" },
          { name: "Qualified outcomes", value: String(row.conversions ?? 0), note: row.ctr ? `CTR ${row.ctr}` : "CTR unavailable until a live sync" },
          { name: "Clicks", value: String(row.clicks ?? 0), note: row.provider_status || "Provider status unavailable" },
        ]}
      />
      <div className="ds-grid wide">
        <Panel title="Campaign plan">
          <Line label="Objective" value={row.objective || "Not recorded"} />
          <Line label="Channel" value={labelize(row.channel)} />
          <Line label="Offer" value="Bound to the approved campaign version" />
          <Line label="Owner" value="Accountable owner comes from the tenant" />
          <Line label="Authorization" value={row.external_campaign_id || row.id.slice(0, 8)} />
          <hr className="rule" />
          <h3>Asset and launch checklist</h3>
          <Checks
            items={[
              { label: "Audience and offer recorded", ok: Boolean(row.objective) },
              { label: "Budget is greater than zero", ok: Number(row.budget) > 0 },
              { label: "Capture source and routing verified", ok: false },
              { label: "Follow-up template activated", ok: row.status === "launched" },
              { label: "Provider result observed", ok: Boolean(row.provider_status) },
            ]}
          />
          <div className="ds-flex" style={{ marginTop: 17 }}>
            <Go href="/content">Open content studio</Go>
            <Go href="/calendar">View calendar</Go>
            <Go href="/insights/attribution">View attribution</Go>
          </div>
        </Panel>
        <Panel title="Budget and execution boundary">
          <div className="between">
            <span className="muted small">Spend against approved ceiling</span>
            <StatusPill tone={Number(row.spent) > Number(row.budget) && Number(row.budget) > 0 ? "blocked" : "success"}>
              {Number(row.budget) > 0 ? "Within recorded budget" : "Budget unavailable"}
            </StatusPill>
          </div>
          <div className="progress" style={{ margin: "16px 0" }}>
            <i style={{ width: Number(row.budget) > 0 ? `${Math.min(100, Math.round((Number(row.spent) / Number(row.budget)) * 100))}%` : "0%" }} />
          </div>
          <Line label="Impressions" value={String(row.impressions ?? "—")} />
          <Line label="Provider" value={row.provider || "Not connected"} />
          <Line label="New channel" value="Manager approval required" />
          <Line label="Budget increase" value="Manager approval required" />
          <Line label="Activation" value="Approved asset plus a working capture path" />
          <hr className="rule" />
          <Go href="/policies">Inspect grant</Go>
        </Panel>
      </div>
    </div>
  );
}
