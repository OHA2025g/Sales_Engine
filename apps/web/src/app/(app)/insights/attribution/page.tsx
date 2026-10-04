"use client";

import { DataTable } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import type { Campaign } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";

export default function AttributionPage() {
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["campaigns"],
    queryFn: async () => (await api<Campaign[]>("/api/v1/lifecycle/campaigns")).data ?? [],
    enabled: can("campaigns.read"),
  });
  if (!can("campaigns.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Loading attribution" />;
  if (query.isError) return <ErrorState message="Campaigns could not be loaded." />;
  const rows = query.data ?? [];
  return (
    <div>
      <PageHeader
        eyebrow="Insights"
        title="Attribution"
        subtitle="Multi-touch attribution is unavailable. The table shows recorded campaign conversions only."
        nextHref="/insights/retention"
        nextLabel="Cohorts"
      />
      <div className="mb-4">
        <StatusPill tone="neutral">Multi-touch unavailable</StatusPill>
      </div>
      {rows.length === 0 ? (
        <EmptyState title="No campaign outcomes" body="A conversion appears after a live metrics sync, not from a product price." />
      ) : (
        <DataTable
          rows={rows}
          columns={[
            { key: "name", header: "Campaign", cell: (row) => row.name },
            { key: "channel", header: "Channel", cell: (row) => row.channel },
            { key: "conversions", header: "Conversions", cell: (row) => String(row.conversions ?? 0) },
          ]}
        />
      )}
    </div>
  );
}
