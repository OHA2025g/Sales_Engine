"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { MetricStrip, StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";

type Retention = { status: string; grr: number | null; nrr: number | null; reason?: string };

export default function CohortsPage() {
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["retention"],
    queryFn: async () => (await api<Retention>("/api/v1/workflow/retention")).data,
    enabled: can("forecast.read"),
  });
  if (!can("forecast.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Loading cohorts" />;
  if (query.isError || !query.data) return <ErrorState message="Retention could not be loaded." />;
  const data = query.data;
  const measured = data.status === "measured" && data.grr != null && data.nrr != null;
  return (
    <div>
      <PageHeader
        eyebrow="Insights"
        title="Cohorts"
        subtitle="GRR and NRR stay unavailable until an opening recurring cohort and later movement exist."
        nextHref="/insights/automation"
        nextLabel="Automation performance"
      />
      <div className="mb-4">
        <StatusPill tone={measured ? "success" : "neutral"}>{measured ? "Measured" : "Unavailable"}</StatusPill>
      </div>
      <MetricStrip
        items={[
          { label: "GRR", value: measured ? `${(data.grr! * 100).toFixed(1)}%` : "Unavailable", hint: data.reason || data.status },
          { label: "NRR", value: measured && data.nrr != null ? `${(data.nrr * 100).toFixed(1)}%` : "Unavailable" },
        ]}
      />
    </div>
  );
}
